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
const rows=[];
for(const gid of Object.keys(gunslots)){
  const inst=GB.sanitize(ctx,gid,defInst(gid)).installed;
  const tree=GB.buildTree(ctx,gid,inst); const N=tree.nodes;
  const L=api.gwBuildLayout({gunId:gid,installed:inst,slots:tree});
  for(const c of L.cells){
    const b=api.gwSidBase(N[c.path].sid);
    if(!/^(scope|mount)$/.test(b) || c.row<=L.body.row) continue;
    const par=N[c.path].parent, pb=par?api.gwSidBase(N[par].sid):"";
    if(/^(handguard|hand_guard|stock)$/.test(pb)) continue;
    const kids=(N[c.path].children||[]).map(k=>api.gwSidBase(N[k].sid));
    rows.push({gun:items[gid].n,base:b,item:(items[inst[c.path]]||{}).n||"",parentBase:pb,row:c.row,col:c.col,kids:kids.join(",")});
  }
}
console.log("total",rows.length);
const byParent={};rows.forEach(r=>{(byParent[r.parentBase]=byParent[r.parentBase]||[]).push(r)});
for(const k of Object.keys(byParent)){
  console.log("== parentBase",k,"count",byParent[k].length);
  byParent[k].forEach(r=>console.log("   ",r.gun.slice(0,28).padEnd(30),r.base,r.row+"c"+r.col,"item="+r.item.slice(0,24).padEnd(26),"kids="+r.kids));
}
