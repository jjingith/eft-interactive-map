const fs=require("fs"),path=require("path");
const ROOT=path.resolve(__dirname,"..");
const GB=require(path.join(ROOT,"gun_builder.js"));
const items=JSON.parse(fs.readFileSync(path.join(ROOT,"data/items.json"),"utf8")).items;
const stats=JSON.parse(fs.readFileSync(path.join(ROOT,"data/gun-stats.json"),"utf8"));
const presets=JSON.parse(fs.readFileSync(path.join(ROOT,"data/gun-presets.json"),"utf8")).presets||{};
const ctx=GB.context(items,stats);
const byGun={};Object.values(presets).forEach(p=>{(byGun[p.g]=byGun[p.g]||[]).push(p)});
function defInst(gid){const def=(stats.guns[gid]||{}).preset;const p=(def&&presets[def]&&presets[def].g===gid)?presets[def]:(byGun[gid]||[])[0];return (p&&p.i)||{};}
const multi="5aa66c72e5b5b00016327c93"; // MagMount Multimount
const atacr="5aa66be6e5b5b0214e506e97";
const gid=Object.keys(items).find(k=>(items[k].n||"").indexOf("SV-98 7.62x54R")===0);
const base=GB.sanitize(ctx,gid,defInst(gid)).installed;
// remove sight_rear if conflicts
delete base["mod_sight_rear"];
const inst=Object.assign({},base,{"mod_scope":multi});
const s=GB.sanitize(ctx,gid,inst);
console.log("multimount kept:", s.installed["mod_scope"]===multi, "dropped:", JSON.stringify(s.dropped||[]));
const t=GB.buildTree(ctx,gid,s.installed);
function dump(p,d){const n=t.nodes[p];if(!n)return;console.log(" ".repeat(d*2)+p+" sid="+n.sid+" label="+n.label+" allow="+(n.allow||[]).length+" kids="+JSON.stringify(n.children||[]));
  (n.children||[]).forEach(k=>dump(k,d+1));}
dump("mod_scope",0);
console.log("--- 物品自身 slots ---");
console.log(JSON.stringify(items[multi].slots||[],null,1));
console.log("--- ATACR slots ---", JSON.stringify(items[atacr].slots||[]));
