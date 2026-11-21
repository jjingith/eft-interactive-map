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
function defInst(gid){const st=(stats.guns||{})[gid]||{}; if(st.preset&&presets[st.preset]) return presets[st.preset].i||{};
  for(const pid in presets){const p=presets[pid]; if(p&&p.g===gid) return p.i||{};} return {};}
function base(s){return String(s||"").replace(/^mod_/,"").replace(/#\d+$/,"").replace(/_\d{3,}$/,"");}
const rows=[];
for(const gid of Object.keys(gunslots)){
  const inst=GB.sanitize(ctx,gid,defInst(gid)).installed;
  const tree=GB.buildTree(ctx,gid,inst); const N=tree.nodes;
  const L=api.gwBuildLayout({gunId:gid,installed:inst,slots:tree});
  const dv=L.cells.filter(c=>c.role==="dovetailMount");
  if(!dv.length) continue;
  const muzzle=L.cells.find(c=>c.row===L.body.row&&base(N[c.path].sid)==="muzzle");
  const fs_=L.cells.find(c=>base(N[c.path].sid)==="sight_front");
  const rs=L.cells.find(c=>base(N[c.path].sid)==="sight_rear");
  const ch=L.cells.find(c=>base(N[c.path].sid)==="charge");
  const kids=(N[dv[0].path].children||[]).map(k=>({sid:N[k].sid,base:base(N[k].sid),item:(items[inst[k]]||{}).n||""}));
  rows.push({gun:items[gid].n,id:gid,
    muzzleCol:muzzle?muzzle.col:null, bodyCol:L.body.col,
    dv:dv.map(c=>({p:c.path,r:c.row,c:c.col})),
    fs:fs_?{r:fs_.row,c:fs_.col}:null, rs:rs?{r:rs.row,c:rs.col}:null, ch:ch?{r:ch.row,c:ch.col}:null,
    kids});
}
console.log("dovetail guns",rows.length);
rows.forEach(r=>console.log(
 ` ${r.gun.slice(0,24).padEnd(26)} bodyC${r.bodyCol} muzzleC${r.muzzleCol} | dv ${JSON.stringify(r.dv)} | fs ${JSON.stringify(r.fs)} rs ${JSON.stringify(r.rs)} ch ${JSON.stringify(r.ch)} | kids ${JSON.stringify(r.kids)}`));
