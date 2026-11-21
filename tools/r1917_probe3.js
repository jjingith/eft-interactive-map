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
const target="622b3c081b89c677a33bcda6";
console.log("item:",items[target].n,"slots:",(items[target].slots||[]).map(s=>s.sid+"/"+s.id));
for(const gid of Object.keys(gunslots)){
  const tree=GB.buildTree(ctx,gid,GB.sanitize(ctx,gid,defInst(gid)).installed);
  for(const p of Object.keys(tree.nodes)){
    if((tree.nodes[p].allow||[]).indexOf(target)<0) continue;
    const inst=Object.assign({},GB.sanitize(ctx,gid,defInst(gid)).installed,{[p]:target});
    const s=GB.sanitize(ctx,gid,inst);
    if(s.installed[p]!==target) continue;
    const t2=GB.buildTree(ctx,gid,s.installed);
    const kids=(t2.nodes[p]||{}).children||[];
    const L=api.gwBuildLayout({gunId:gid,installed:s.installed,slots:t2});
    const direct=L.cells.filter(c=>c.path.indexOf(p+"/")===0&&c.path.split("/").length===p.split("/").length+1);
    console.log("host",items[gid].n,"slot",p,"kids",kids.length,"directCells",direct.length);
    console.log("  kid sids:",kids.map(k=>t2.nodes[k].sid));
    console.log("  direct:",direct.map(c=>c.path.split("/").pop()+" r"+c.row+"c"+c.col));
    console.log("  all cells with prefix:",L.cells.filter(c=>c.path.indexOf(p+"/")===0).map(c=>c.path.slice(p.length+1)+" r"+c.row+"c"+c.col));
    break;
  }
}
