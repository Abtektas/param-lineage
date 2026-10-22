// node --test test/
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const A = require('../src/analyze.js');

const data = JSON.parse(fs.readFileSync(path.join(__dirname, '../data/v1.17.0_to_v1.18.0-rc1.json')));
const fixture = (name) => fs.readFileSync(path.join(__dirname, 'fixtures', name), 'utf8');
const values = (text) => new Map(A.parseParamsFile(text).rows.map((r) => [r.name, r.value]));
const byCategory = (report, category) => report.findings.filter((f) => f.category === category).map((f) => f.name).sort();

// v1.17.0_sihsim_quadx_custom.params: saved from v1.17.0 SITL (SIH quad) after setting
// EKF2_GPS_DELAY=150 EKF2_GPS_POS_X=0.12 EKF2_GPS_POS_Y=-0.05 COM_RC_OVERRIDE=0 MPC_LAND_RC_HELP=1
// MPC_XY_VEL_MAX=8 RC1_REV=-1 RC3_REV=-1 COM_KILL_DISARM=3.
// v1.18.0-rc1_inplace_upgrade.params: all parameters of v1.18.0-rc1 SITL started on the v1.17.0
// parameter storage of that vehicle, so PX4 itself converted them.

test('the corrected file gives the values of an in-place upgrade', () => {
  const report = A.analyze(fixture('v1.17.0_sihsim_quadx_custom.params'), data);
  const corrected = values(A.correctedFile(report, data, { useNewDefaults: true }));
  const inplace = values(fixture('v1.18.0-rc1_inplace_upgrade.params'));
  const differences = [...inplace].filter(([name, v]) => corrected.has(name) && Math.fround(corrected.get(name)) !== Math.fround(v));
  assert.deepEqual(differences.map(([n]) => n), ['_HASH_CHECK']);
  for (const name of ['SENS_GPS0_DELAY', 'SENS_GPS1_DELAY', 'SENS_GPS0_OFFX', 'SENS_GPS0_OFFY', 'MAN_OVERRIDE_SPD', 'MPC_AUTO_NUDGING', 'RC1_REV', 'RC3_REV', 'NAV_ACC_RAD']) {
    assert.equal(Math.fround(corrected.get(name)), Math.fround(inplace.get(name)), name);
  }
  // every parameter the corrected file sets exists on the upgraded vehicle; the unused baro
  // calibration slots (0) are only listed by PX4 once something sets them
  const extra = [...corrected.keys()].filter((n) => !inplace.has(n));
  assert.deepEqual(extra, ['CAL_BARO1_ID', 'CAL_BARO2_ID', 'CAL_BARO3_ID']);
  assert.deepEqual(extra.map((n) => corrected.get(n)), [0, 0, 0]);
});

test('findings for the SITL file', () => {
  const report = A.analyze(fixture('v1.17.0_sihsim_quadx_custom.params'), data);
  assert.deepEqual(report.airframe, { id: 10040, name: '10040_sihsim_quadx', removed: false });
  assert.deepEqual(byCategory(report, 'migrated'), ['COM_RC_OVERRIDE', 'EKF2_GPS_DELAY', 'EKF2_GPS_POS_X', 'EKF2_GPS_POS_Y', 'MPC_LAND_RC_HELP']);
  assert.deepEqual(byCategory(report, 'removed'), ['COM_KILL_DISARM']);
  assert.deepEqual(byCategory(report, 'revertsDefault'), ['FD_ACT_EN', 'MPC_LAND_RADIUS', 'NAV_ACC_RAD', 'SENS_MAG_AUTOCAL']);
  assert.equal(byCategory(report, 'typeFix').length, 18);
  assert.deepEqual(byCategory(report, 'unknown'), []);
  assert.deepEqual(byCategory(report, 'outOfRange'), []);
  assert.deepEqual(byCategory(report, 'boardSpecific'), ['PWM_MAIN_FUNC10', 'PWM_MAIN_FUNC11', 'PWM_MAIN_FUNC12', 'PWM_MAIN_FUNC13',
    'PWM_MAIN_FUNC14', 'PWM_MAIN_FUNC15', 'PWM_MAIN_FUNC16', 'PWM_MAIN_FUNC9']);
});

test('without the option, the corrected file keeps the old defaults the file has', () => {
  const report = A.analyze(fixture('v1.17.0_sihsim_quadx_custom.params'), data);
  const corrected = values(A.correctedFile(report, data));
  assert.equal(corrected.get('NAV_ACC_RAD'), 2);
  assert.equal(corrected.get('FD_ACT_EN'), 1);
});

const line = (name, value, type) => `1\t1\t${name}\t${value}\t${type}`;

test('conversions repeat param_translation.cpp of v1.18.0-rc1', () => {
  const text = [
    line('MNT_RANGE_PITCH', '120.000000000000000000', 9),
    line('MOT_POLE_COUNT', '12', 6),
    line('MPC_LAND_RC_HELP', '1', 6),
    line('EKF2_GPS_DELAY', '87.900001525878906250', 9),
    line('COM_RC_OVERRIDE', '3', 6),
    line('RC2_REV', '-1.000000000000000000', 9),
  ].join('\n');
  const corrected = values(A.correctedFile(A.analyze(text, data), data));
  assert.equal(corrected.get('MNT_MAX_PITCH'), 60);
  assert.equal(corrected.get('MNT_MIN_PITCH'), -60);
  for (let i = 1; i <= 12; i++) assert.equal(corrected.get(`DSHOT_MOT_POL${i}`), 12);
  assert.equal(corrected.get('MPC_AUTO_NUDGING'), 2);
  assert.equal(corrected.get('SENS_GPS0_DELAY'), 87); // static_cast<int32_t> truncates
  assert.equal(corrected.has('MAN_OVERRIDE_SPD'), false); // only "disabled" is converted
  assert.equal(corrected.get('RC2_REV'), -1);
  for (const old of ['MNT_RANGE_PITCH', 'MOT_POLE_COUNT', 'MPC_LAND_RC_HELP', 'EKF2_GPS_DELAY', 'COM_RC_OVERRIDE']) assert.equal(corrected.has(old), false);
});

test('RC*_REV written as integers in the file is fine', () => {
  const report = A.analyze(line('RC1_REV', '-1', 6), data);
  assert.deepEqual(report.findings, []);
});

test('replaced parameters are suggested, not written', () => {
  const text = [line('EKF2_AGP_CTRL', '1', 6), line('EKF2_AGP_NOISE', '2.5', 9), line('SENS_IMU_TEMP', '60', 9),
    line('DSHOT_BIDIR_EN', '1', 6), line('PWM_MAIN_TIM0', '-3', 6), line('PWM_MAIN_TIM1', '400', 6)].join('\n');
  const report = A.analyze(text, data);
  const removed = Object.fromEntries(report.findings.filter((f) => f.category === 'removed').map((f) => [f.name, f.suggestions]));
  assert.deepEqual(removed.EKF2_AGP_CTRL, [{ name: 'EKF2_AGP0_CTRL', value: 1 }]);
  assert.deepEqual(removed.SENS_IMU_TEMP, [{ name: 'HEATER1_TEMP', value: 60 }]);
  assert.deepEqual(removed.DSHOT_BIDIR_EN, [{ name: 'PWM_MAIN_TIM0', value: -6, from: -3 }]);
  const corrected = values(A.correctedFile(report, data));
  assert.equal(corrected.has('EKF2_AGP0_CTRL'), false);
  assert.equal(corrected.has('HEATER1_TEMP'), false);
  assert.equal(corrected.get('PWM_MAIN_TIM0'), -3);
});

test('a removed parameter on its old default loses nothing', () => {
  const report = A.analyze([line('COM_KILL_DISARM', '5.000000000000000000', 9), line('BAT3_I_CHANNEL', '-1', 6), line('BAT3_I_CHANNEL', '4', 6)].join('\n'), data);
  assert.deepEqual(report.findings.map((f) => `${f.name}:${f.category}`), ['COM_KILL_DISARM:removedDefault', 'BAT3_I_CHANNEL:removedDefault', 'BAT3_I_CHANNEL:removed']);
});

test('ranges are compared as float32', () => {
  assert.deepEqual(A.analyze(line('EKF2_MIN_RNG', '0.009999999776482582', 9), data).findings, []);
});

test('only a range the new release narrowed is reported', () => {
  // MPC_MANTHR_MIN: 0..1 in v1.17.0, 0..0.5 in v1.18.0-rc1
  assert.deepEqual(A.analyze(line('MPC_MANTHR_MIN', '0.600000023841857910', 9), data).findings.map((f) => f.category), ['outOfRange']);
  assert.deepEqual(A.analyze(line('MPC_MANTHR_MIN', '0.5', 9), data).findings, []);
  // outside the same range in v1.17.0 already (MC_YAW_P 0..5), and a volatile counter
  assert.deepEqual(A.analyze(line('MC_YAW_P', '6.5', 9), data).findings, []);
  assert.deepEqual(A.analyze(line('EKF2_MIN_RNG', '0.005', 9), data).findings, []);
  assert.deepEqual(A.analyze(line('LND_FLIGHT_T_LO', '-2062199228', 6), data).findings, []);
});

test('other formats and components', () => {
  const report = A.analyze('# Version: 1.16.1 \nMPC_XY_VEL_MAX,8\n1\t154\tCAM_PARAM\t1\t6\nnot a line here at all\n', data);
  assert.equal(report.versionMatches, false);
  assert.deepEqual(report.counts, { total: 2, autopilot: 1, other: 1, skipped: 1 });
  const corrected = A.correctedFile(report, data);
  assert.match(corrected, /^1\t1\tMPC_XY_VEL_MAX\t8\t9$/m);
  assert.match(corrected, /^1\t154\tCAM_PARAM\t1\t6$/m);
});

test('a different airframe number uses that airframe\'s defaults', () => {
  // VTOL 13000 never had the multicopter NAV_ACC_RAD default of 2
  const vtol = A.analyze([line('SYS_AUTOSTART', '13000', 6), line('NAV_ACC_RAD', '2.000000000000000000', 9)].join('\n'), data);
  assert.deepEqual(vtol.findings, []);
  const quad = A.analyze([line('SYS_AUTOSTART', '4001', 6), line('NAV_ACC_RAD', '2.000000000000000000', 9)].join('\n'), data);
  assert.deepEqual(quad.findings.map((f) => [f.name, f.category, f.newDefault]), [['NAV_ACC_RAD', 'revertsDefault', 10]]);
});
