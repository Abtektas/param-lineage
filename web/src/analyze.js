// Checks a QGroundControl .params file saved from one PX4 release against the parameters of a
// newer release. Pure functions, used by the page and by the tests (node).
(function (root) {
  'use strict';

  const AUTOPILOT_COMPONENT = 1;
  const MAV_PARAM_TYPE = { i: 6, f: 9 }; // INT32, REAL32

  const f32 = (x) => Math.fround(x);
  const sameF32 = (a, b) => f32(a) === f32(b);
  // compared as float32, the type PX4 stores: 0.01 is saved as 0.009999999776
  const outside = (value, min, max) => (min != null && f32(value) < f32(min)) || (max != null && f32(value) > f32(max));

  function formatValue(value, type) {
    if (type === 'i') return String(Math.trunc(value));
    return String(parseFloat(f32(value).toPrecision(9)));
  }

  // Same line format QGroundControl accepts when loading a file (ParameterEditorController):
  // '#' lines are comments, fields are split on tabs, spaces or commas, and a line has either
  // five fields (QGC: vehicle, component, name, value, type) or two (Mission Planner: name, value).
  function parseParamsFile(text) {
    const header = {};
    const rows = [];
    const skipped = [];
    text.split(/\r?\n/).forEach((line, index) => {
      const trimmed = line.trim();
      if (trimmed.startsWith('#')) {
        const m = trimmed.match(/^#\s*(Stack|Vehicle|Version|Git Revision):\s*(.*)$/);
        if (m) header[m[1]] = m[2].trim();
        return;
      }
      if (!trimmed) return;
      const f = trimmed.split(/[\t ,]+/);
      if (f.length === 5) {
        rows.push({ line: index + 1, vehicle: +f[0], component: +f[1], name: f[2], valueText: f[3], mavType: +f[4] });
      } else if (f.length === 2) {
        rows.push({ line: index + 1, vehicle: null, component: AUTOPILOT_COMPONENT, name: f[0], valueText: f[1], mavType: null });
      } else {
        skipped.push({ line: index + 1, text: trimmed });
      }
    });
    rows.forEach((r) => { r.value = Number(r.valueText); });
    return { header, rows, skipped };
  }

  function versionOf(header) {
    const m = (header.Version || '').match(/^(\d+)\.(\d+)\.(\d+)/);
    return m ? { major: +m[1], minor: +m[2], patch: +m[3], text: header.Version } : null;
  }

  // The conversions PX4's param_translation.cpp applies on an in-place upgrade, for the
  // "migrated" notes. Returns [{name, value}] or [] when the firmware would not set anything.
  function applyRule(rule, value, fileValues, target) {
    switch (rule.type) {
      case 'rename':
        return [{ name: rule.to, value }];
      case 'copy':
        return rule.to.map((name) => ({ name, value }));
      case 'copy_int':
        return rule.to.map((name) => ({ name, value: Math.trunc(value) }));
      case 'half_range':
        return value > 0 ? [{ name: rule.max, value: f32(value) * 0.5 }, { name: rule.min, value: -f32(value) * 0.5 }] : [];
      case 'if_zero_set':
        return value === 0 ? [{ name: rule.to, value: rule.value }] : [];
      case 'if_nonzero_set_bit': {
        if (value === 0) return [];
        const base = fileValues.has(rule.to) ? fileValues.get(rule.to) : target[rule.to].d;
        return [{ name: rule.to, value: base | (1 << rule.bit) }];
      }
      default:
        return [];
    }
  }

  // Suggestions for "replaced" notes: values the user can set by hand. Never written to the
  // corrected file, because PX4 itself does not convert these.
  function suggest(rule, value, rows) {
    if (!rule) return [];
    switch (rule.type) {
      case 'suggest_rename':
        return [{ name: rule.to, value }];
      case 'suggest_scale':
        return [{ name: rule.to, value: value * rule.factor }];
      case 'bdshot_hint': {
        if (value === 0) return [];
        const bdshot = { '-5': -8, '-4': -7, '-3': -6 };
        return rows
          .filter((r) => /^PWM_(MAIN|AUX)_TIM\d+$/.test(r.name) && String(r.value) in bdshot)
          .map((r) => ({ name: r.name, value: bdshot[String(r.value)], from: r.value }));
      }
      default:
        return [];
    }
  }

  function describeValue(meta, value) {
    if (!meta) return '';
    const option = (meta.v || []).find(([v]) => v === value);
    return option ? option[1] : '';
  }

  // Instance numbers replaced, so PWM_MAIN_FUNC9 matches PWM_MAIN_FUNC1. The metadata lists the
  // instances of one reference board, and a vehicle can have more (SITL has 16 main outputs).
  const family = (name) => name.replace(/\d+/g, '#');
  const INTERNAL = new Set(['_HASH_CHECK']);

  function familyIndex(data) {
    if (!data._families) {
      const removedFamilies = new Map();
      for (const name of Object.keys(data.notes)) if (!removedFamilies.has(family(name))) removedFamilies.set(family(name), name);
      data._families = { target: new Set(Object.keys(data.target).map(family)), removed: removedFamilies };
    }
    return data._families;
  }

  function analyze(text, data, options = {}) {
    const parsed = parseParamsFile(text);
    const { notes, typeRules, target, source, removedMeta } = data;
    const families = familyIndex(data);
    const version = versionOf(parsed.header);
    const autopilotRows = parsed.rows.filter((r) => r.component === AUTOPILOT_COMPONENT);
    const otherRows = parsed.rows.filter((r) => r.component !== AUTOPILOT_COMPONENT);
    const fileValues = new Map(autopilotRows.map((r) => [r.name, r.value]));

    // The defaults a file can silently undo: those of its airframe (SYS_AUTOSTART) when the
    // airframe is a PX4 one, otherwise the plain parameter defaults.
    const autostart = fileValues.get('SYS_AUTOSTART');
    const airframeData = autostart ? data.airframes[String(autostart)] : undefined;
    const airframe = autostart ? { id: autostart, name: airframeData ? airframeData.name : null, removed: !!(airframeData && airframeData.removed) } : null;
    const defaultChange = (name) => {
      if (airframeData && airframeData.changes) return airframeData.changes[name] || null;
      const src = source[name];
      const dst = target[name];
      if (!src || !dst || src[1] === undefined || dst.d === undefined || sameF32(src[1], dst.d)) return null;
      return [src[1], dst.d];
    };

    const findings = [];
    const add = (category, row, extra) => findings.push({ category, name: row.name, value: row.value, valueText: row.valueText, line: row.line, ...extra });

    for (const row of autopilotRows) {
      const note = notes[row.name];
      if (note) {
        const old = removedMeta[row.name];
        const onOldDefault = old && old.d !== undefined && sameF32(row.value, old.d);
        const onFixedValue = note.fixed !== undefined && sameF32(row.value, note.fixed);
        if (note.kind === 'migrated') {
          // A file that already has the new name (saved from a newer build) keeps its own value;
          // the bitmask rule already merged it.
          const writes = applyRule(note.rule, row.value, fileValues, target)
            .filter((w) => !fileValues.has(w.name) || note.rule.type === 'if_nonzero_set_bit');
          add(onOldDefault ? 'removedDefault' : 'migrated', row, { note, writes, oldDefault: old.d });
        } else if (onOldDefault || onFixedValue) {
          add('removedDefault', row, { note, oldDefault: old.d });
        } else {
          add('removed', row, { note, suggestions: suggest(note.rule, row.value, autopilotRows), oldDefault: old.d, oldMeta: old });
        }
        continue;
      }

      const meta = target[row.name];
      if (!meta) {
        const removedSibling = families.removed.get(family(row.name));
        if (INTERNAL.has(row.name)) add('internal', row, {});
        else if (removedSibling) {
          const old = removedMeta[removedSibling];
          const onOldDefault = old.d !== undefined && sameF32(row.value, old.d);
          add(onOldDefault ? 'removedDefault' : 'removed', row, { note: notes[removedSibling], sibling: removedSibling, suggestions: [], oldDefault: old.d });
        }
        else if (families.target.has(family(row.name))) add('boardSpecific', row, {});
        else add('unknown', row, {});
        continue;
      }
      if (Number.isNaN(row.value)) {
        add('unreadable', row, { meta });
        continue;
      }

      const typeRule = typeRules[row.name];
      const isIntegerText = /^[+-]?\d+$/.test(row.valueText);
      if (typeRule && meta.t === 'i' && !isIntegerText) {
        add('typeFix', row, { rule: typeRule, newValue: row.value < 0 ? -1 : 1 });
        continue;
      }

      const change = defaultChange(row.name);
      if (change && sameF32(row.value, change[0])) {
        add('revertsDefault', row, { oldDefault: change[0], newDefault: change[1], meta, fromAirframe: !!(airframeData && airframeData.changes) });
      }
      // Only a range the new release narrowed: QGroundControl loads a file without checking ranges,
      // so a value already outside the old range is not new. Volatile parameters are written by the
      // firmware itself (LND_FLIGHT_T_LO holds an unsigned count in an int32).
      const oldRange = source[row.name];
      if (!meta.vol && outside(row.value, meta.min, meta.max) && !(oldRange && outside(row.value, oldRange[2], oldRange[3]))) {
        add('outOfRange', row, { meta });
      }
    }

    return {
      header: parsed.header,
      version,
      airframe,
      expectedSource: data.from.tag,
      versionMatches: !version || `v${version.major}.${version.minor}` === data.from.tag.replace(/^(v\d+\.\d+).*/, '$1'),
      counts: { total: parsed.rows.length, autopilot: autopilotRows.length, other: otherRows.length, skipped: parsed.skipped.length },
      otherComponents: [...new Set(otherRows.map((r) => r.component))],
      skipped: parsed.skipped,
      findings,
      parsed,
    };
  }

  // A copy of the file the target release can load: removed parameters dropped, the values PX4
  // migrates on an in-place upgrade written under their new names, and RC*_REV written as integers.
  function correctedFile(report, data, options = {}) {
    const { parsed, findings } = report;
    const findingsOf = new Map();
    for (const f of findings) findingsOf.set(f.line, [...(findingsOf.get(f.line) || []), f]);
    const firstQgc = parsed.rows.find((r) => r.vehicle !== null);
    const vehicleId = firstQgc ? firstQgc.vehicle : 1;
    const out = [];
    const written = new Set();

    for (const row of parsed.rows) {
      const rowFindings = row.component === AUTOPILOT_COMPONENT ? findingsOf.get(row.line) || [] : [];
      const f = (category) => rowFindings.find((x) => x.category === category);
      const removal = f('removed') || f('removedDefault') || f('migrated');
      if (removal) {
        for (const w of removal.writes || []) {
          const meta = data.target[w.name];
          written.add(w.name);
          out.push({ vehicle: row.vehicle ?? vehicleId, component: AUTOPILOT_COMPONENT, name: w.name,
                     valueText: formatValue(w.value, meta.t), mavType: MAV_PARAM_TYPE[meta.t], generated: true });
        }
        continue;
      }
      if (f('typeFix')) {
        out.push({ ...row, valueText: String(f('typeFix').newValue), mavType: MAV_PARAM_TYPE.i });
        continue;
      }
      const reverts = f('revertsDefault');
      const fixed = reverts && options.useNewDefaults ? { ...row, valueText: formatValue(reverts.newDefault, reverts.meta.t) } : { ...row };
      const meta = row.component === AUTOPILOT_COMPONENT ? data.target[row.name] : null;
      if (fixed.mavType === null && meta) {
        fixed.vehicle = vehicleId;
        fixed.mavType = MAV_PARAM_TYPE[meta.t];
      }
      out.push(fixed);
    }

    // A migrated value is merged with the file's own value of that parameter (MPC_AUTO_NUDGING
    // bits), so it replaces the original line.
    const result = out.filter((r) => r.generated || !(r.component === AUTOPILOT_COMPONENT && written.has(r.name)));
    result.sort((a, b) => a.component - b.component || (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));

    const lines = [];
    const h = parsed.header;
    lines.push(`# Onboard parameters for Vehicle ${vehicleId}`, '#');
    for (const key of ['Stack', 'Vehicle', 'Version', 'Git Revision']) if (h[key]) lines.push(`# ${key}: ${h[key]}`);
    lines.push('#', `# Converted for PX4 ${data.to.tag} by param-lineage. Check it before loading.`);
    lines.push('# Vehicle-Id Component-Id Name Value Type');
    for (const r of result) {
      if (r.mavType === null) lines.push(`${r.name},${r.valueText}`);
      else lines.push(`${r.vehicle ?? vehicleId}\t${r.component}\t${r.name}\t${r.valueText}\t${r.mavType}`);
    }
    return lines.join('\n') + '\n';
  }

  const api = { parseParamsFile, analyze, correctedFile, applyRule, describeValue, formatValue };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.PX4ParamUpgrade = api;
})(this);
