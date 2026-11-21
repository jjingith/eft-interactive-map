const fs=require("fs"),path=require("path");
const ROOT=path.resolve(__dirname,"..");
const GB=require(path.join(ROOT,"gun_builder.js"));
const items=JSON.parse(fs.readFileSync(path.join(ROOT,"data/items.json"),"utf8")).items;
const stats=JSON.parse(fs.readFileSync(path.join(ROOT,"data/gun-stats.json"),"utf8"));
const presets=JSON.parse(fs.readFileSync(path.join(ROOT,"data/gun-presets.json"),"utf8")).presets||{};
const src=fs.readFileSync(path.join(ROOT,"app.js"),"utf8");
const block=src.slice(src.indexOf("function gwSidBase("),src.indexOf("function renderGunSkin("));
const api=new Function("itemRec","GW_ITEM_MAP",block+"\nreturn {gwBuildLayout:gwBuildLayout,gwSidBase:gwSidBase,gwIsBadSlot:gwIsBadSlot};")(
  function(id){return items[id]||null;},items);
const ctx=GB.context(items,stats);
const byGun={};Object.values(presets).forEach(p=>{(byGun[p.g]=byGun[p.g]||[]).push(p)});
function defInst(gid){const def=(stats.guns[gid]||{}).preset;const p=(def&&presets[def]&&presets[def].g===gid)?presets[def]:(byGun[gid]||[])[0];return (p&&p.i)||{};}
let badGuns=[];
for(const gid of Object.keys(byGun)){
  const inst=defInst(gid);
  const tree=GB.buildTree(ctx,gid,inst);
  const L=api.gwBuildLayout({gunId:gid,installed:inst,slots:tree});
  const bads=L.cells.filter(c=>api.gwIsBadSlot(tree.nodes[c.path]));
  if(bads.length) badGuns.push({gun:items[gid].n,paths:bads.map(b=>({p:b.path,r:b.row,c:b.col}))});
}
console.log("BAD guns:",badGuns.length);
console.log(JSON.stringify(badGuns.slice(0,10),null,1));
