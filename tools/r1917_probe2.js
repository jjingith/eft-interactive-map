const fs=require("fs"),path=require("path");
const ROOT=path.resolve(__dirname,"..");
const GB=require(path.join(ROOT,"gun_builder.js"));
const items=JSON.parse(fs.readFileSync(path.join(ROOT,"data/items.json"),"utf8")).items;
const stats=JSON.parse(fs.readFileSync(path.join(ROOT,"data/gun-stats.json"),"utf8"));
const presets=JSON.parse(fs.readFileSync(path.join(ROOT,"data/gun-presets.json"),"utf8")).presets||{};
const src=fs.readFileSync(path.join(ROOT,"app.js"),"utf8");
const block=src.slice(src.indexOf("function gwSidBase("),src.indexOf("function renderGunSkin("));
const api=new Function("itemRec","GW_ITEM_MAP",block+"\nreturn {gwBuildLayout:gwBuildLayout,gwSidBase:gwSidBase};")(
  function(id){return items[id]||null;},items);
const ctx=GB.context(items,stats);
const byGun={};Object.values(presets).forEach(p=>{(byGun[p.g]=byGun[p.g]||[]).push(p)});
function defInst(gid){const def=(stats.guns[gid]||{}).preset;const p=(def&&presets[def]&&presets[def].g===gid)?presets[def]:(byGun[gid]||[])[0];return (p&&p.i)||{};}
const multi="5aa66c72e5b5b00016327c93", atacr="5aa66be6e5b5b0214e506e97";
const base="57ae0171245977343c27bfcf"; // 第一个 allow 里应是基座？
const gid=Object.keys(items).find(k=>(items[k].n||"").indexOf("SV-98 7.62x54R")===0);
let inst=GB.sanitize(ctx,gid,defInst(gid)).installed;
delete inst["mod_sight_rear"]; inst["mod_scope"]=multi;
let s=GB.sanitize(ctx,gid,inst);
function show(tag,installed){
  const L=api.gwBuildLayout({gunId:gid,installed,slots:GB.buildTree(ctx,gid,installed)});
  console.log("== "+tag+" rows="+L.rows+" pad="+L.topPad+" exc="+JSON.stringify(L.exceptions.slice(0,2)));
  L.cells.filter(c=>c.path==="mod_scope"||c.path.startsWith("mod_scope/")).forEach(c=>{
    const item=installed[c.path]||"";
    console.log("   ",c.path,"r"+c.row,"c"+c.col,(items[item]||{}).n||"");
  });
  return L;
}
show("A: mount only",s.installed);
// install 34mm ATACR into _000 and a micro base into _001
const t=GB.buildTree(ctx,gid,s.installed);
const kid000="mod_scope/mod_scope_000", kid001="mod_scope/mod_scope_001";
console.log("kid001 allow:",(t.nodes[kid001].allow||[]).map(id=>(items[id]||{}).n));
const baseId=(t.nodes[kid001].allow||[]).find(id=>/Aimpoint Micro瞄具基座/.test((items[id]||{}).n||""));
let inst2=Object.assign({},s.installed,{[kid000]:atacr});
if(baseId) inst2[kid001]=baseId;
let s2=GB.sanitize(ctx,gid,inst2);
console.log("installed:",Object.entries(s2.installed).filter(([k])=>k.startsWith("mod_scope")).map(([k,v])=>k+"="+(items[v]||{}).n));
const L2=show("B: ATACR + base",s2.installed);
// then its child sight
const t2=GB.buildTree(ctx,gid,s2.installed);
const grand=(t2.nodes[kid001]||{}).children||[];
console.log("base children:",grand.map(g=>g+" allow="+((t2.nodes[g].allow||[]).length)));
