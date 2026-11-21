const fs=require("fs"),path=require("path");
const ROOT=path.resolve(__dirname,"..");
const GB=require(path.join(ROOT,"gun_builder.js"));
const items=JSON.parse(fs.readFileSync(path.join(ROOT,"data/items.json"),"utf8")).items;
const stats=JSON.parse(fs.readFileSync(path.join(ROOT,"data/gun-stats.json"),"utf8"));
const presets=JSON.parse(fs.readFileSync(path.join(ROOT,"data/gun-presets.json"),"utf8")).presets||{};
const src=fs.readFileSync(path.join(ROOT,"app.js"),"utf8");
const block=src.slice(src.indexOf("function gwSidBase("),src.indexOf("function renderGunSkin("));
const api=new Function("itemRec","GW_ITEM_MAP",block+"\nreturn {gwBuildLayout:gwBuildLayout,gwSidBase:gwSidBase};")(function(id){return items[id]||null;},items);
const ctx=GB.context(items,stats);
const byGun={};Object.values(presets).forEach(p=>{(byGun[p.g]=byGun[p.g]||[]).push(p)});
function defInst(gid){const def=(stats.guns[gid]||{}).preset;const p=(def&&presets[def]&&presets[def].g===gid)?presets[def]:(byGun[gid]||[])[0];return (p&&p.i)||{};}
let n=0,out=[];
for(const gid of Object.keys(byGun)){
  const inst=GB.sanitize(ctx,gid,defInst(gid)).installed;
  const L=api.gwBuildLayout({gunId:gid,installed:inst,slots:GB.buildTree(ctx,gid,inst)});
  if(L.topPad>0){
    n++;
    const minCells=L.cells.filter(c=>c.row===1).map(c=>c.path.split("/").slice(-2).join("/"));
    out.push({gun:items[gid].n,pad:L.topPad,rows:L.rows,topRow:minCells.slice(0,4)});
  }
}
console.log("guns with topPad>0:",n,"/",Object.keys(byGun).length);
out.slice(0,12).forEach(x=>console.log(" ",x.gun,"pad",x.pad,"rows",x.rows,"top:",JSON.stringify(x.topRow)));
