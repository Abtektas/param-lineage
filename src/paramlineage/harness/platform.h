// SPDX-License-Identifier: BSD-3-Clause
// Stand-in for PX4's platform headers (px4_platform_common/log.h, defines.h, posix.h and
// px4_config.h), as far as a release's param_translation.cpp and the headers it includes use them.
// paramlineage.translations writes those four headers at build time; each includes this file.
#pragma once

#include <errno.h>

#ifndef __EXPORT
#define __EXPORT
#endif

#define PX4_OK 0
#define PX4_ERROR (-1)
#define OK 0

// The two PX4_ISFINITE lines and M_PI_PRECISE below are PX4's, copied from
// platforms/common/include/px4_platform_common/defines.h because the compiled code uses them
// by these names. Copyright (c) 2012 - 2025, PX4 Development Team, BSD-3-Clause; see
// LICENSE-THIRD-PARTY.
#ifdef __cplusplus
static inline constexpr bool PX4_ISFINITE(float x) { return __builtin_isfinite(x); }
static inline constexpr bool PX4_ISFINITE(double x) { return __builtin_isfinite(x); }
#endif

// The translation code only logs. The harness records the line that logged.
void pl_logged(int line);
#define PX4_INFO(...) pl_logged(__LINE__)
#define PX4_WARN(...) pl_logged(__LINE__)
#define PX4_ERR(...) pl_logged(__LINE__)
#define PX4_DEBUG(...) do {} while (0)
#define PX4_PANIC(...) pl_logged(__LINE__)

// PX4's, from defines.h of v1.14 to v1.16, whose matrix headers use it (see above)
#ifndef M_PI_PRECISE
#define M_PI_PRECISE 3.141592653589793238462643383279502884
#endif
