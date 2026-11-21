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
const gid=Object.keys(items).find(k=>(items[k].n||"").indexOf("DS Arms SA-58")===0);
const mpr="5649a2464bdc2d91118b45a8";
let inst=GB.sanitize(ctx,gid,defInst(gid)).installed;
const tree0=GB.buildTree(ctx,gid,inst);
const mprSlot=Object.keys(tree0.nodes).find(p=>(tree0.nodes[p].allow||[]).includes(mpr));
console.log("MPR slot:",mprSlot);
inst[mprSlot]=mpr;
let s=GB.sanitize(ctx,gid,inst);
// layer2: child scope + base
let t=GB.buildTree(ctx,gid,s.installed);
let kids=(t.nodes[mprSlot]||{}).children||[];
console.log("layer2 slots:",kids);
if(kids.length){
  const k=kids[0];
  const baseId=(t.nodes[k].allow||[]).find(id=>/(瞄具基座|基座环|Micro)/.test((items[id]||{}).n||""));
  if(baseId){ s=GB.sanitize(ctx,gid,Object.assign({},s.installed,{[k]:baseId})); console.log("layer2 installed:",items[baseId].n); }
}
// layer3: grandchild scope
t=GB.buildTree(ctx,gid,s.installed);
const gk=[];
Object.keys(t.nodes).forEach(p=>{if(p.startsWith(mprSlot+"/")&&(t.nodes[p].children||[]).length===0&&(t.nodes[p].allow||[]).length) gk.push(p);});
console.log("candidate leaf slots:",gk);
for(const g of gk){
  const sc=(t.nodes[g].allow||[]).find(id=>String((items[id]||{}).pt||"")==="Scope");
  if(sc){ s=GB.sanitize(ctx,gid,Object.assign({},s.installed,{[g]:sc})); console.log("layer3 installed",g,"=",items[sc].n); break; }
}
function show(tag,installed){
  const L=api.gwBuildLayout({gunId:gid,installed,slots:GB.buildTree(ctx,gid,installed)});
  console.log("== "+tag+" rows="+L.rows+" topPad="+L.topPad+" body=r"+L.body.row);
  L.cells.filter(c=>c.path===mprSlot||c.path.startsWith(mprSlot+"/")).forEach(c=>console.log("   ",c.path.replace(/^.*?mod_handguard/,"hg"),"r"+c.row,"c"+c.col));
  return L;
}
show("with 3 layers",s.installed);
// remove layer3+2 → back to base
let s2=GB.sanitize(ctx,gid,Object.assign({},inst));
show("after removing layers",s2.installed);
