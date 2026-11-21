const fs=require("fs"),path=require("path");
const ROOT=path.resolve(__dirname,"..");
const GB=require(path.join(ROOT,"gun_builder.js"));
const items=JSON.parse(fs.readFileSync(path.join(ROOT,"data/items.json"),"utf8")).items;
const stats=JSON.parse(fs.readFileSync(path.join(ROOT,"data/gun-stats.json"),"utf8"));
const presets=JSON.parse(fs.readFileSync(path.join(ROOT,"data/gun-presets.json"),"utf8")).presets||{};
const ctx=GB.context(items,stats);
const byGun={};Object.values(presets).forEach(p=>{(byGun[p.g]=byGun[p.g]||[]).push(p)});
function defInst(gid){const def=(stats.guns[gid]||{}).preset;const p=(def&&presets[def]&&presets[def].g===gid)?presets[def]:(byGun[gid]||[])[0];return (p&&p.i)||{};}
const multi="5aa66c72e5b5b00016327c93";
const gid=Object.keys(items).find(k=>(items[k].n||"").indexOf("SV-98 7.62x54R")===0);
let inst=GB.sanitize(ctx,gid,defInst(gid)).installed;
delete inst["mod_sight_rear"];
inst["mod_scope"]=multi;
const s=GB.sanitize(ctx,gid,inst);
const t=GB.buildTree(ctx,gid,s.installed);
const kids=(t.nodes["mod_scope"]||{}).children||[];
console.log("kept mount:",s.installed["mod_scope"]===multi);
console.log("direct children:",kids.length,kids.map(k=>t.nodes[k].sid+"@"+k));
