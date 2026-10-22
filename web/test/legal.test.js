// The terms are part of the program: the license files, the README and the page must keep them.
const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');

const WEB = path.join(__dirname, '..');
const REPO = path.join(WEB, '..');
const read = (dir, name) => fs.readFileSync(path.join(dir, name), 'utf8');

test('both license texts are present and complete', () => {
  for (const [name, holder] of [['LICENSE', 'the param-lineage contributors'], ['LICENSE-THIRD-PARTY', 'PX4 Development Team']]) {
    const text = read(REPO, name);
    assert.match(text, /^BSD 3-Clause License/, name);
    assert.ok(text.includes(holder), name);
    assert.ok(text.includes('IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE'), name);
  }
});

test('the README keeps the safety and liability terms', () => {
  // compare with line breaks folded, so wrapping the README does not matter
  const readme = read(REPO, 'README.md').replace(/\s+/g, ' ');
  for (const phrase of ['## Safety and liability', 'accept no liability and no responsibility',
    'does not approve a vehicle as safe or airworthy', 'not affiliated with or endorsed by the PX4 project',
    'PX4 is a trademark of Dronecode Project, Inc.', 'LICENSE-THIRD-PARTY']) {
    assert.ok(readme.includes(phrase), phrase);
  }
});

test('the page shows the terms and embeds both license texts', () => {
  const page = read(WEB, 'src/page.html');
  for (const phrase of ['without warranty of any kind', 'accept no liability and no responsibility',
    'not an airworthiness approval', 'Not affiliated with or endorsed by the PX4 project',
    'PX4 is a trademark of Dronecode Project, Inc.', 'copyright PX4 Development Team',
    'LICENSES.project', 'LICENSES.px4']) {
    assert.ok(page.includes(phrase), phrase);
  }
  const build = read(WEB, 'tools/build_page.py');
  assert.ok(build.includes('"LICENSE"') && build.includes('"LICENSE-THIRD-PARTY"') && build.includes('/*__LICENSES__*/null'));
});
