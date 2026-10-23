// SPDX-License-Identifier: BSD-3-Clause
// Runs a PX4 release's param_modify_on_import() (src/lib/parameters/param_translation.cpp) on
// stored values and prints what it does. paramlineage.translations builds it with the release's
// own headers and that file, unchanged; see docs/DESIGN.md, "2. Translations".
//
//   harness <parameters> < <probes>
//
// <parameters>: a line "NAME i|f VALUE" for each parameter of the release, sorted by name.
// <probes>: a line "NAME i|f VALUE" for each stored value to import (i: BSON int32, f: BSON double).
// Prints one JSON line for each probe the code touched, then one line with the counts, what the
// function returns for a value it leaves alone, and the source lines reached.
//
// The parameter API follows PX4's src/lib/parameters/parameters.cpp: param_find returns the index
// of the name in the sorted list, or PARAM_INVALID; param_set and param_get copy four bytes as the
// parameter's type and return PX4_ERROR for PARAM_INVALID.
//
// Each probe runs three times: as described, with the handles numbered in reverse, and with the
// bytes of the node that the BSON decoder does not write filled in. Results that differ name what
// they depend on, because a firmware build numbers its parameters differently and the decoder
// leaves those bytes from the value before.

#include <cerrno>
#include <cfloat>
#include <cinttypes>
#include <climits>
#include <cmath>
#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <errno.h>
#include <float.h>
#include <inttypes.h>
#include <limits.h>
#include <math.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/types.h>

#include <algorithm>
#include <set>
#include <string>
#include <utility>
#include <vector>

// Everything param_translation.cpp includes (its #include lines, written by
// paramlineage.translations), so that the recording macros below do not reach those headers.
#include <px4_platform_common/defines.h>
#include <px4_platform_common/log.h>
#include "translation_includes.h"

namespace
{

struct Param {
	std::string name;
	bool is_float;
	int32_t i;
	float f;
};

std::vector<Param> g_params;
bool g_reverse_handles = false;

// What one run of a probe did.
struct Run {
	std::vector<std::pair<size_t, Param>> undo;
	std::vector<std::string> calls;
	std::vector<std::pair<const char *, int>> matched;
	std::set<std::pair<std::string, int>> reached;
	bool name_matched = false;
	bool api_called = false;
};

Run *g_run = nullptr;

void reached(const char *what, int line)
{
	if (g_run != nullptr) { g_run->reached.insert({what, line}); }
}

std::string json_string(const char *s)
{
	std::string out = "\"";

	for (; *s; ++s) {
		unsigned char c = static_cast<unsigned char>(*s);

		if (c == '"' || c == '\\') {
			out += '\\';
			out += static_cast<char>(c);

		} else if (c < 0x20 || c >= 0x7f) {
			char buf[8];
			std::snprintf(buf, sizeof(buf), "\\u%04x", c);
			out += buf;

		} else {
			out += static_cast<char>(c);
		}
	}

	return out + "\"";
}

std::string json_float(double v)
{
	if (std::isnan(v)) { return "\"nan\""; }

	if (std::isinf(v)) { return v > 0 ? "\"inf\"" : "\"-inf\""; }

	char buf[64];
	std::snprintf(buf, sizeof(buf), "%.9g", static_cast<double>(static_cast<float>(v)));
	return buf;
}

std::string json_int(int64_t v)
{
	char buf[32];
	std::snprintf(buf, sizeof(buf), "%" PRId64, v);
	return buf;
}

std::string value_of(const Param &p)
{
	return p.is_float ? json_float(p.f) : json_int(p.i);
}

param_t handle_of(size_t index)
{
	return static_cast<param_t>(g_reverse_handles ? g_params.size() - 1 - index : index);
}

bool index_of(param_t handle, size_t *index)
{
	if (handle == PARAM_INVALID || static_cast<size_t>(handle) >= g_params.size()) { return false; }

	*index = g_reverse_handles ? g_params.size() - 1 - handle : handle;
	return true;
}

std::string call(int line, const char *what)
{
	return "{\"line\":" + std::to_string(line) + ",\"call\":\"" + what + "\"";
}

param_t pl_param_find(const char *name, int line)
{
	g_run->api_called = true;
	reached("param_find", line);
	auto it = std::lower_bound(g_params.begin(), g_params.end(), name,
	[](const Param & p, const char *n) { return std::strcmp(p.name.c_str(), n) < 0; });
	bool found = it != g_params.end() && it->name == name;
	g_run->calls.push_back(call(line, "param_find") + ",\"name\":" + json_string(name) + ",\"found\":" +
			       (found ? "true" : "false") + "}");
	return found ? handle_of(it - g_params.begin()) : PARAM_INVALID;
}

int pl_param_set(param_t handle, const void *val, const char *what, int line)
{
	g_run->api_called = true;
	reached(what, line);
	size_t index;

	if (!index_of(handle, &index) || val == nullptr) {
		g_run->calls.push_back(call(line, what) + ",\"param\":null,\"result\":" + std::to_string(PX4_ERROR) + "}");
		return PX4_ERROR;
	}

	Param &p = g_params[index];
	g_run->undo.push_back({index, p});

	if (p.is_float) { std::memcpy(&p.f, val, sizeof(p.f)); }

	else { std::memcpy(&p.i, val, sizeof(p.i)); }

	g_run->calls.push_back(call(line, what) + ",\"param\":" + json_string(p.name.c_str()) + ",\"value\":" + value_of(p) +
			       ",\"result\":" + std::to_string(PX4_OK) + "}");
	return PX4_OK;
}

int pl_param_get(param_t handle, void *val, int line)
{
	g_run->api_called = true;
	reached("param_get", line);
	size_t index;

	if (!index_of(handle, &index) || val == nullptr) {
		g_run->calls.push_back(call(line, "param_get") + ",\"param\":null,\"result\":" + std::to_string(PX4_ERROR) + "}");
		return PX4_ERROR;
	}

	const Param &p = g_params[index];

	if (p.is_float) { std::memcpy(val, &p.f, sizeof(p.f)); }

	else { std::memcpy(val, &p.i, sizeof(p.i)); }

	g_run->calls.push_back(call(line, "param_get") + ",\"param\":" + json_string(p.name.c_str()) + ",\"value\":" +
			       value_of(p) + ",\"result\":" + std::to_string(PX4_OK) + "}");
	return PX4_OK;
}

int pl_strcmp(const char *a, const char *b, int line)
{
	int r = std::strcmp(a, b);

	if (r == 0) {
		g_run->matched.push_back({"strcmp", line});
		g_run->name_matched = true;
		reached("strcmp", line);
	}

	return r;
}

int pl_strncmp(const char *a, const char *b, size_t n, int line)
{
	int r = std::strncmp(a, b, n);

	if (r == 0) {
		g_run->matched.push_back({"strncmp", line});
		reached("strncmp", line);
	}

	return r;
}

template <class C> C *pl_strstr(C *a, const char *b, int line)
{
	C *r = std::strstr(a, b);

	if (r != nullptr) {
		g_run->matched.push_back({"strstr", line});
		reached("strstr", line);
	}

	return r;
}

char *pl_strcpy(char *a, const char *b, int line)
{
	reached("strcpy", line);
	return std::strcpy(a, b);
}

char *pl_strncpy(char *a, const char *b, size_t n, int line)
{
	reached("strncpy", line);
	return std::strncpy(a, b, n);
}

char *pl_strcat(char *a, const char *b, int line)
{
	reached("strcat", line);
	return std::strcat(a, b);
}

int pl_snprintf(int line, char *buf, size_t n, const char *format, ...)
{
	reached("snprintf", line);
	va_list args;
	va_start(args, format);
	int r = std::vsnprintf(buf, n, format, args);
	va_end(args);
	return r;
}

} // namespace

void pl_logged(int line)
{
	reached("log", line);
}

#define strcmp(a, b) pl_strcmp((a), (b), __LINE__)
#define strncmp(a, b, n) pl_strncmp((a), (b), (n), __LINE__)
#define strstr(a, b) pl_strstr((a), (b), __LINE__)
#define strcpy(a, b) pl_strcpy((a), (b), __LINE__)
#define strncpy(a, b, n) pl_strncpy((a), (b), (n), __LINE__)
#define strcat(a, b) pl_strcat((a), (b), __LINE__)
#define snprintf(...) pl_snprintf(__LINE__, __VA_ARGS__)
#define param_find(name) pl_param_find((name), __LINE__)
#define param_set(param, val) pl_param_set((param), (val), "param_set", __LINE__)
#define param_set_no_notification(param, val) pl_param_set((param), (val), "param_set_no_notification", __LINE__)
#define param_get(param, val) pl_param_get((param), (val), __LINE__)

#ifdef PL_NUTTX
#define __PX4_NUTTX
#endif

#include "param_translation.cpp"

#undef strcmp
#undef strncmp
#undef strstr
#undef strcpy
#undef strncpy
#undef strcat
#undef snprintf
#undef param_find
#undef param_set
#undef param_set_no_notification
#undef param_get

namespace
{

// v1.12 keeps an integer in node->i (int64), later releases in node->i32.
template <class N> auto set_int(N *n, int32_t v, int) -> decltype(n->i32, void()) { n->i32 = v; }
template <class N> void set_int(N *n, int32_t v, long) { n->i = v; }
template <class N> auto get_int(const N *n, int) -> decltype(n->i32, int64_t()) { return n->i32; }
template <class N> int64_t get_int(const N *n, long) { return n->i; }

// Up to v1.14 param_modify_on_import() returns a bool, from v1.15 an enum.
bool modified(bool r) { return r; }
std::string result_json(bool r) { return r ? "true" : "false"; }

// what the function returns for a value it leaves alone
bool unmodified(bool) { return false; }

template <class R> bool modified(R r) { return r != R::PARAM_NOT_MODIFIED; }
template <class R> R unmodified(R) { return R::PARAM_NOT_MODIFIED; }
template <class R> std::string result_json(R r)
{
	if (r == R::PARAM_SKIP_IMPORT) { return "\"PARAM_SKIP_IMPORT\""; }

	if (r == R::PARAM_NOT_MODIFIED) { return "\"PARAM_NOT_MODIFIED\""; }

	if (r == R::PARAM_MODIFIED) { return "\"PARAM_MODIFIED\""; }

	return std::to_string(static_cast<int>(r));
}

struct Probe {
	char name[BSON_MAXNAME];
	bool is_float;
	int32_t i;
	double d;
};

void make_node(bson_node_s *node, const Probe &probe, bool fill)
{
	if (fill) {
		std::memset(node, 'X', sizeof(*node));
		node->d = 12345.678; // what an earlier double would leave in the bytes an int32 does not write

	} else {
		std::memset(node, 0, sizeof(*node));
	}

	std::strcpy(node->name, probe.name);

	if (probe.is_float) {
		node->type = BSON_DOUBLE;
		node->d = probe.d;

	} else {
		node->type = BSON_INT32;
		set_int(node, probe.i, 0);
	}
}

std::string node_json(const bson_node_s &node)
{
	std::string out = "{\"name\":" + json_string(node.name) + ",\"type\":";

	if (node.type == BSON_INT32) { return out + "\"i\",\"value\":" + json_int(get_int(&node, 0)) + "}"; }

	if (node.type == BSON_DOUBLE) { return out + "\"f\",\"value\":" + json_float(node.d) + "}"; }

	return out + std::to_string(static_cast<int>(node.type)) + "}";
}

bool same_node(const bson_node_s &a, const bson_node_s &b)
{
	return std::strcmp(a.name, b.name) == 0 && a.type == b.type && std::memcmp(&a.d, &b.d, sizeof(a.d)) == 0;
}

// One run of a probe: the JSON of what happened, and whether the code touched it.
std::string run_probe(const Probe &probe, bool fill, bool reverse_handles, Run *run, bool *touched)
{
	g_reverse_handles = reverse_handles;
	g_run = run;
	bson_node_s node;
	make_node(&node, probe, fill);
	bson_node_s before = node;
	auto r = param_modify_on_import(&node);
	g_run = nullptr;

	// back to the defaults for the next run
	for (auto it = run->undo.rbegin(); it != run->undo.rend(); ++it) { g_params[it->first] = it->second; }
	*touched = run->name_matched || run->api_called || modified(r) || !same_node(before, node);
	std::string out = "\"return\":" + result_json(r) + ",\"node\":" + node_json(node) + ",\"matched\":[";

	for (size_t k = 0; k < run->matched.size(); ++k) {
		out += std::string(k ? "," : "") + "[\"" + run->matched[k].first + "\"," + std::to_string(run->matched[k].second) + "]";
	}

	out += "],\"calls\":[";

	for (size_t k = 0; k < run->calls.size(); ++k) { out += (k ? "," : "") + run->calls[k]; }

	return out + "]";
}

bool read_value(const char *kind, const char *text, Probe *probe)
{
	char *end = nullptr;
	errno = 0;

	if (std::strcmp(kind, "i") == 0) {
		long long v = std::strtoll(text, &end, 10);

		if (errno || *end || v < INT32_MIN || v > INT32_MAX) { return false; }

		probe->is_float = false;
		probe->i = static_cast<int32_t>(v);
		return true;
	}

	if (std::strcmp(kind, "f") == 0) {
		double v = std::strtod(text, &end);

		if (errno || *end) { return false; }

		probe->is_float = true;
		probe->d = v;
		return true;
	}

	return false;
}

} // namespace

int main(int argc, char **argv)
{
	if (argc != 2) {
		std::fprintf(stderr, "usage: harness <parameters> < <probes>\n");
		return 2;
	}

	FILE *f = std::fopen(argv[1], "r");

	if (f == nullptr) {
		std::fprintf(stderr, "cannot open %s\n", argv[1]);
		return 2;
	}

	char name[64], kind[8], text[64];

	while (std::fscanf(f, "%63s %7s %63s", name, kind, text) == 3) {
		Probe value{};

		if (!read_value(kind, text, &value)) {
			std::fprintf(stderr, "bad parameter line: %s %s %s\n", name, kind, text);
			return 2;
		}

		if (!g_params.empty() && std::strcmp(g_params.back().name.c_str(), name) >= 0) {
			std::fprintf(stderr, "parameters are not sorted at %s\n", name);
			return 2;
		}

		g_params.push_back({name, value.is_float, value.i, static_cast<float>(value.d)});
	}

	std::fclose(f);

	if (g_params.size() >= PARAM_INVALID) {
		std::fprintf(stderr, "too many parameters\n");
		return 2;
	}

	std::set<std::pair<std::string, int>> all_reached;
	long probes = 0, touched_probes = 0;

	while (std::scanf("%63s %7s %63s", name, kind, text) == 3) {
		Probe probe{};

		if (std::strlen(name) >= sizeof(probe.name) || !read_value(kind, text, &probe)) {
			std::fprintf(stderr, "bad probe line: %s %s %s\n", name, kind, text);
			return 2;
		}

		std::strcpy(probe.name, name);
		++probes;

		Run base, reversed, filled;
		bool touched, touched_reversed, touched_filled;
		std::string out = run_probe(probe, false, false, &base, &touched);
		std::string out_reversed = run_probe(probe, false, true, &reversed, &touched_reversed);
		std::string out_filled = run_probe(probe, true, false, &filled, &touched_filled);
		all_reached.insert(base.reached.begin(), base.reached.end());

		std::string depends;

		if (out_reversed != out) { depends += "\"parameter handles\""; }

		if (out_filled != out) { depends += std::string(depends.empty() ? "" : ",") + "\"node bytes\""; }

		if (!touched && depends.empty()) { continue; }

		++touched_probes;
		std::printf("{\"name\":%s,\"type\":\"%s\",\"value\":%s,%s,\"depends_on\":[%s]}\n", json_string(name).c_str(), kind,
			    text, out.c_str(), depends.c_str());
	}

	const auto untouched = unmodified(decltype(param_modify_on_import(nullptr)) {});

	std::printf("{\"probes\":%ld,\"touched\":%ld,\"untouched_return\":%s,\"reached\":[", probes, touched_probes,
		    result_json(untouched).c_str());
	bool first = true;

	for (const auto &r : all_reached) {
		std::printf("%s[\"%s\",%d]", first ? "" : ",", r.first.c_str(), r.second);
		first = false;
	}

	std::printf("]}\n");
	return 0;
}
