import { moduleUrl } from './browser_modules.mjs';
const {sfenAfterMove} = await import(moduleUrl('shogi.js'));
let data=''; for await (const chunk of process.stdin) data+=chunk;
process.stdout.write(JSON.stringify(JSON.parse(data).map(([sfen,usi])=>sfenAfterMove(sfen,usi))));
