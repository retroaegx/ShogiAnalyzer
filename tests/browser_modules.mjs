import fs from 'node:fs';
const cache = new Map();
export function moduleUrl(relative) {
  if (cache.has(relative)) return cache.get(relative);
  let text = fs.readFileSync(new URL('../server/assets_web/js/'+relative, import.meta.url),'utf8');
  text = text.replace(/from ["']\/js\/([^"']+)["']/g, (_,path) => `from "${moduleUrl(path)}"`);
  const url = 'data:text/javascript;base64,'+Buffer.from(text).toString('base64');
  cache.set(relative,url);
  return url;
}
