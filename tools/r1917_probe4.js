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
function defInst(gid){const def=(stats.guns[gid]||{}).preset;const p=(def&&presets[def]&&presets[def].g===gid)?presets[def]:(byGun[gid]||[])[0];return (p&&p.i)||{};}
for(const target of ["6165adcdd3a39d50044c120f","676149fbe2cf1419500357ee"]){
  console.log("==== ",items[target].n,"declared",(items[target].slots||[]).length);
  console.log("  sids:",(items[target].slots||[]).map(s=>s.sid));
  for(const gid of Object.keys(gunslots)){
    const tree=GB.buildTree(ctx,gid,GB.sanitize(ctx,gid,defInst(gid)).installed);
    const p=Object.keys(tree.nodes).find(k=>(tree.nodes[k].allow||[]).indexOf(target)>=0);
    if(!p) continue;
    const inst=Object.assign({},GB.sanitize(ctx,gid,defInst(gid)).installed,{[p]:target});
    const s=GB.sanitize(ctx,gid,inst);
    if(s.installed[p]!==target) continue;
    const t2=GB.buildTree(ctx,gid,s.installed);
    const kids=(t2.nodes[p]||{}).children||[];
    const vis=kids.filter(k=>api.gwSlotVisible({installed:s.installed,slots:t2},k));
    console.log("  host",items[gid].n,"| kids",kids.length,"visible",vis.length);
    console.log("   hidden:",kids.filter(k=>vis.indexOf(k)<0).map(k=>k.split("/").pop()+" sid="+t2.nodes[k].sid));
    break;
  }
}
