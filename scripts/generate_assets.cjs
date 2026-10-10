// Deterministic vector artwork. Render with Node and sharp; PNGs ship with the bot.
const fs = require('node:fs');
const path = require('node:path');
const sharp = require(process.env.WORKSPACE_NODE_MODULES ? path.join(process.env.WORKSPACE_NODE_MODULES, 'sharp') : 'sharp');
const out = path.resolve(__dirname, '../assets');
fs.mkdirSync(out, {recursive: true});
let seed = 365;
const rand = () => { seed = (seed * 1664525 + 1013904223) >>> 0; return seed / 4294967296; };
function branch(x, y, len, angle, depth) {
  const nx = x + Math.cos(angle)*len, ny = y + Math.sin(angle)*len;
  let svg = `<path d="M${x} ${y} Q${x+8} ${y-15} ${nx} ${ny}" fill="none" stroke="url(#wood)" stroke-width="${Math.max(2,depth*5)}" stroke-linecap="round"/>`;
  if (depth > 0) {
    svg += branch(nx, ny, len*.74, angle-.35-rand()*.18, depth-1);
    svg += branch(nx, ny, len*.73, angle+.35+rand()*.18, depth-1);
  } else {
    for (let k=0; k<5; k++) {
      const lx=nx+(rand()-.5)*52, ly=ny+(rand()-.5)*38;
      svg += `<ellipse cx="${lx}" cy="${ly}" rx="${7+rand()*7}" ry="${4+rand()*4}" fill="${['#f8dc70','#c99131','#f4bd4c','#fff0a1'][Math.floor(rand()*4)]}" transform="rotate(${rand()*140-70} ${lx} ${ly})"/>`;
    }
  }
  return svg;
}
let gold = `<svg xmlns="http://www.w3.org/2000/svg" width="900" height="900" viewBox="0 0 900 900"><defs><radialGradient id="bg"><stop stop-color="#294635"/><stop offset="1" stop-color="#102820"/></radialGradient><linearGradient id="wood"><stop stop-color="#9b612a"/><stop offset=".5" stop-color="#e8b94e"/><stop offset="1" stop-color="#ffe5a0"/></linearGradient></defs><rect width="900" height="900" fill="url(#bg)"/><circle cx="450" cy="365" r="320" fill="none" stroke="#d4a347" opacity=".35"/><circle cx="450" cy="365" r="298" fill="none" stroke="#d4a347" opacity=".15"/><ellipse cx="450" cy="762" rx="210" ry="24" fill="#071e17"/>`;
gold += branch(450,750,150,-Math.PI/2,6);
gold += `<path d="M450 720 Q410 750 355 762 M450 720 Q475 755 545 761 M450 730 L450 771" stroke="url(#wood)" stroke-width="12" fill="none" stroke-linecap="round"/><text x="450" y="823" text-anchor="middle" font-family="Georgia,serif" font-size="36" fill="#f8df90">365</text><text x="450" y="857" text-anchor="middle" font-family="sans-serif" font-size="16" letter-spacing="4" fill="#bfa86b">LIBRARYBOT</text></svg>`;
const forest = `<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="300" viewBox="0 0 1000 300"><rect width="1000" height="300" fill="#183b2c"/><circle cx="790" cy="77" r="43" fill="#e4cc85"/><path d="M0 225 Q230 120 480 222 Q750 130 1000 200 L1000 300 L0 300Z" fill="#285540"/><path d="M0 270 Q250 190 490 270 Q770 220 1000 250 L1000 300 L0 300Z" fill="#346449"/><g fill="#113324">${[70,150,235,690,870,950].map((x,i)=>`<path d="M${x} ${105+i%3*20} l-42 98 h28 v40 h28 v-40 h28Z"/>`).join('')}</g><text x="480" y="132" text-anchor="middle" font-family="Georgia,serif" font-size="48" fill="#f2e5bc">LibraryBot</text><text x="480" y="178" text-anchor="middle" font-family="sans-serif" font-size="18" fill="#c5d5b5">Лес знаний растёт каждый день</text></svg>`;
(async()=>{ for (const [name, svg] of [['golden-tree',gold],['forest',forest]]) { fs.writeFileSync(path.join(out,name+'.svg'),svg); await sharp(Buffer.from(svg)).png().toFile(path.join(out,name+'.png')); } })().catch(e=>{process.stderr.write(e.message);process.exit(1)});
