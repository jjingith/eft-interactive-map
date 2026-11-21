const fs=require("fs"),path=require("path");
const ROOT=path.resolve(__dirname,"..");
const GB=require(path.join(ROOT,"gun_builder.js"));
const items=JSON.parse(fs.readFileSync(path.join(ROOT,"data/items.json"),"utf8")).items;
const stats=JSON.parse(fs.readFileSync(path.join(ROOT,"data/gun-stats.json"),"utf8"));
const presets=JSON.parse(fs.readFileSync(path.join(ROOT,"data/gun-presets.json"),"utf8")).presets||{};
const gunslots=JSON.parse(fs.readFileSync(path.join(ROOT,"data/gunslots.json"),"utf8")).guns;
const src=fs.readFileSync(path.join(ROOT,"app.js"),"utf8");
const block=src.slice(src.indexOf("function gwSidBase("),src.indexOf("function renderGunSkin("));
const api=new Function("itemRec","GW_ITEM_MAP",block+"\nreturn {gwBuildLayout:gwBuildLayout,gwSidBase:gwSidBase,gwSlotVisible:gwSlotVisible};")(function(id){return items[id]||null;},items);
const ctx=GB.context(items,stats);
const byGun={};Object.values(presets).forEach(p=>{(byGun[p.g]=byGun[p.g]||[]).push(p)});
function defInst(gid){const st=(stats.guns||{})[gid]||{}; if(st.preset&&presets[st.preset]) return presets[st.preset].i||{};
  for(const pid in presets){const p=presets[pid]; if(p&&p.g===gid) return p.i||{};} return {};}
function base(s){return String(s||"").replace(/^mod_/,"").replace(/#\d+$/,"").replace(/_\d{3,}$/,"");}
const rows=[];
for(const gid of Object.keys(gunslots)){
  const inst=GB.sanitize(ctx,gid,defInst(gid)).installed;
  const tree=GB.buildTree(ctx,gid,inst); const N=tree.nodes;
  const L=api.gwBuildLayout({gunId:gid,installed:inst,slots:tree});
  const dv=[];
  L.cells.forEach(c=>{
    if(c.role!=="dovetailMount") return;
    const allow=(N[c.path].allow||[]);
    const scopes=allow.filter(a=>String((items[a]||{}).pt||"")==="Scope");
    dv.push({slot:c.path,row:c.row,col:c.col,ordinal:c.row2Ordinal,
      scopeCount:scopes.length, first:(items[scopes[0]]||{}).n,
      row2:L.cells.filter(x=>x.row===c.row).map(x=>x.col).sort((a,b)=>a-b)});
  });
  if(dv.length) rows.push({gun:items[gid].n,id:gid,rows:L.rows,pad:L.topPad,dv,
    exc:L.exceptions.filter(e=>/燕尾槽/.test(e.why||"")).length});
}
console.log("guns with dovetail mount:",rows.length);
rows.slice(0,12).forEach(r=>{
  r.dv.forEach(d=>console.log(` ${r.gun.slice(0,26).padEnd(28)} ${d.slot.padEnd(22)} r${d.row}c${d.col} ordinal=${d.ordinal} scopes=${d.scopeCount} row2cols=${JSON.stringify(d.row2)}`));
});
const ords=rows.flatMap(r=>r.dv.map(d=>d.ordinal));
const cnt={};ords.forEach(o=>cnt[o]=(cnt[o]||0)+1);
console.log("ordinal distribution:",JSON.stringify(cnt));
