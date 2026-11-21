const fs=require("fs"),path=require("path");
const ROOT=path.resolve(__dirname,"..");
const GB=require(path.join(ROOT,"gun_builder.js"));
const items=JSON.parse(fs.readFileSync(path.join(ROOT,"data/items.json"),"utf8")).items;
const stats=JSON.parse(fs.readFileSync(path.join(ROOT,"data/gun-stats.json"),"utf8"));
const presets=JSON.parse(fs.readFileSync(path.join(ROOT,"data/gun-presets.json"),"utf8")).presets||{};
const gunslots=JSON.parse(fs.readFileSync(path.join(ROOT,"data/gunslots.json"),"utf8")).guns;
const src=fs.readFileSync(path.join(ROOT,"app.js"),"utf8");
const block=src.slice(src.indexOf("function gwSidBase("),src.indexOf("function renderGunSkin("));
const api=new Function("itemRec","GW_ITEM_MAP",block+"\nreturn {gwBuildLayout:gwBuildLayout,gwSidBase:gwSidBase};")(function(id){return items[id]||null;},items);
const ctx=GB.context(items,stats);
const byGun={};Object.values(presets).forEach(p=>{(byGun[p.g]=byGun[p.g]||[]).push(p)});
function defInst(gid){const def=(stats.guns[gid]||{}).preset;const p=(def&&presets[def]&&presets[def].g===gid)?presets[def]:(byGun[gid]||[])[0];return (p&&p.i)||{};}
function base(sid){return String(sid||"").replace(/^mod_/,"").replace(/#\d+$/,"").replace(/_\d{3,}$/,"");}
for(const gid of Object.keys(gunslots)){
  const inst=GB.sanitize(ctx,gid,defInst(gid)).installed;
  const tree=GB.buildTree(ctx,gid,inst); const N=tree.nodes;
  const L=api.gwBuildLayout({gunId:gid,installed:inst,slots:tree});
  const byP={}; L.cells.forEach(c=>byP[c.path]=c);
  const rows=L.rows, pad=L.topPad||0;
  for(const p of Object.keys(N)){
    const n=N[p];
    if(base(n.sid)!=="mount") continue;
    const sc=(n.children||[]).filter(k=>base(N[k].sid)==="scope")[0];
    if(!sc) continue;
    const c=byP[p], s=byP[sc];
    const pn=n.parent?byP[n.parent]:null;
    console.log(`${items[gid].n.slice(0,26).padEnd(28)} mount ${p.slice(-28).padEnd(30)} r${c?c.row:"-"}c${c?c.col:"-"} | scope r${s?s.row:"-"}c${s?s.col:"-"} | parent r${pn?pn.row:"-"}c${pn?pn.col:"-"} | body r${L.body.row}c${L.body.col}`);
  }
}
