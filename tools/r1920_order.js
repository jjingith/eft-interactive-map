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
const TAC=/^(tactical|flashlight|laser|devices|emitter)$/;
let checked=0, bad=[], rows2=[];
for(const gid of Object.keys(gunslots)){
  const inst=GB.sanitize(ctx,gid,defInst(gid)).installed;
  const tree=GB.buildTree(ctx,gid,inst);
  const L=api.gwBuildLayout({gunId:gid,installed:inst,slots:tree});
  const pad=L.topPad||0;
  const on=function(base,row){return L.cells.filter(c=>c.row===row&&api.gwSidBase(tree.nodes[c.path].sid)===base);};
  const tac=L.cells.filter(c=>c.row===2+pad&&TAC.test(api.gwSidBase(tree.nodes[c.path].sid))&&!tree.nodes[c.path].parent);
  if(!tac.length) continue;
  checked++;
  const fs_=on("sight_front",2+pad)[0], sc=on("scope",2+pad)[0], rs=on("sight_rear",2+pad)[0];
  tac.forEach(t=>{
    if(fs_ && !(t.col>fs_.col)) bad.push({gun:items[gid].n,why:"战术在准星左侧",tac:t.col,fs:fs_.col});
    if(sc && !(t.col<sc.col)) bad.push({gun:items[gid].n,why:"战术在瞄具右侧",tac:t.col,scope:sc.col});
  });
  if(sc && rs && !(sc.col<rs.col)) bad.push({gun:items[gid].n,why:"瞄具在照门右侧",scope:sc.col,rs:rs.col});
  rows2.push({gun:items[gid].n,fs:fs_&&fs_.col,sc:sc&&sc.col,tac:tac.map(t=>t.col),rs:rs&&rs.col});
}
console.log("guns with top-row tactical:",checked,"violations:",bad.length);
bad.slice(0,5).forEach(b=>console.log("  ",b));
rows2.slice(0,8).forEach(r=>console.log("  ",r.gun,"准星c"+r.fs,"战术"+JSON.stringify(r.tac),"瞄具c"+r.sc,"照门c"+r.rs));
