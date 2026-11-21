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
const gid=Object.keys(items).find(k=>(items[k].n||"").indexOf("SV-98 7.62x54R")===0);
let inst=GB.sanitize(ctx,gid,defInst(gid)).installed;
delete inst["mod_sight_rear"];
inst["mod_scope"]=multi;
let s1=GB.sanitize(ctx,gid,inst);
console.log("A) mount only:");
let L=api.gwBuildLayout({gunId:gid,installed:s1.installed,slots:GB.buildTree(ctx,gid,s1.installed)});
L.cells.forEach(c=>console.log("  ",c.path,"r"+c.row,"c"+c.col,"lane="+c.lane));
// install ATACR in main child
const inst2=Object.assign({},s1.installed,{"mod_scope/mod_scope_000":atacr});
let s2=GB.sanitize(ctx,gid,inst2);
console.log("B) mount + ATACR in _000:", s2.installed["mod_scope/mod_scope_000"]===atacr);
L=api.gwBuildLayout({gunId:gid,installed:s2.installed,slots:GB.buildTree(ctx,gid,s2.installed)});
L.cells.forEach(c=>console.log("  ",c.path,"r"+c.row,"c"+c.col,"lane="+c.lane));
console.log("exceptions:",JSON.stringify(L.exceptions));
