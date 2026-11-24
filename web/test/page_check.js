// Drives the built page like a user (needs jsdom 30.1.2: npm install jsdom@30.1.2 in a scratch folder,
// then NODE_PATH=<that folder>/node_modules node test/page_check.js).
const { JSDOM } = require('jsdom');
const fs = require('fs');
const T = require('path').join(__dirname, '..');
const html = fs.readFileSync(`${T}/dist/param-lineage-upgrade-check-v1.17.0-to-v1.18.0.html`, 'utf8');
const A = require(`${T}/src/analyze.js`);
const data = JSON.parse(fs.readFileSync(`${T}/data/v1.17.0_to_v1.18.0.json`));

async function load(name, text) {
  const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true });
  const w = dom.window;
  const errors = [];
  w.addEventListener('error', (e) => errors.push(e.message));
  const input = w.document.getElementById('file');
  Object.defineProperty(input, 'files', { value: [new w.File([text], name, { type: 'text/plain' })] });
  input.dispatchEvent(new w.Event('change'));
  for (let i = 0; i < 50 && !w.document.querySelector('#result section'); i++) await new Promise((r) => setTimeout(r, 20));
  return { w, errors };
}

(async () => {
  const text = fs.readFileSync(`${T}/test/fixtures/v1.17.0_sihsim_quadx_custom.params`, 'utf8');
  const { w, errors } = await load('my_quad.params', text);
  const d = w.document;
  const sections = [...d.querySelectorAll('#result section')].map((s) => s.querySelector('h2').textContent);
  console.log('sections:', sections);
  console.log('stats:', [...d.querySelectorAll('.stat')].map((s) => s.textContent).join(' | '));
  console.log('banners:', [...d.querySelectorAll('.banner')].map((b) => b.textContent));
  const lost = [...d.querySelectorAll('#result section')][1];
  console.log('lost rows:', [...lost.querySelectorAll('tbody tr')].map((tr) => tr.querySelector('td').textContent.slice(0, 40)));
  // download with the new-defaults option
  let blob;
  w.URL.createObjectURL = (b) => { blob = b; return 'blob:test'; };
  w.URL.revokeObjectURL = () => {};
  d.getElementById('newdefaults').click();
  [...d.querySelectorAll('button')].find((b) => b.textContent.includes('Download')).click();
  const downloaded = await blob.text();
  const expected = A.correctedFile(A.analyze(text, data), data, { useNewDefaults: true });
  console.log('download equals correctedFile(useNewDefaults):', downloaded === expected, downloaded.length);
  console.log('errors:', errors);
  const footer = d.getElementById('footer').textContent;
  const licenses = [...d.querySelectorAll('#footer pre')].map((p) => p.textContent);
  console.log('terms in footer:', footer.includes('accept no liability and no responsibility'), footer.includes('PX4 is a trademark'),
    'license texts equal files:', licenses[0] === fs.readFileSync(`${T}/../LICENSE`, 'utf8'), licenses[1] === fs.readFileSync(`${T}/../LICENSE-THIRD-PARTY`, 'utf8'));

  // a crafted file must not inject markup
  const evil = '# Version: 1.17.0 <b>x</b>\n1\t1\t<img/src=x/onerror=window.pwned=1>\t5\t6\n1\t1\tEKF2_AGP_CTRL\t1\t6\n';
  const r2 = await load('<svg onload=window.pwned=2>.params', evil);
  await new Promise((r) => setTimeout(r, 50));
  console.log('injection (pwned, img/svg elements, errors):', r2.w.pwned, r2.w.document.querySelectorAll('#result img, #result svg').length, r2.errors);
  console.log('decision text:', [...r2.w.document.querySelectorAll('#result section')].map((s) => s.querySelector('h2').textContent));
})();
