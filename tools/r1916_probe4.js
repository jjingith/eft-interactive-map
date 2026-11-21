const fs=require("fs"),path=require("path");
const ROOT=path.resolve(__dirname,"..");
const GB=require(path.join(ROOT,"gun_builder.js"));
const items=JSON.parse(fs.readFileSync(path.join(ROOT,"data/items.json"),"utf8")).items;
const stats=JSON.parse(fs.readFileSync(path.join(ROOT,"data/gun-stats.json"),"utf8"));
const presets=JSON.parse(fs.readFileSync(path.join(ROOT,"data/gun-presets.json"),"utf8")).presets||{};
const src=fs.readFileSync(path.join(ROOT,"app.js"),"utf8");
const block=src.slice(src.indexOf("function gwSidBase("),src.indexOf("function renderGunSkin("));
const api=new Function("itemRec","GW_ITEM_MAP",block+"\nreturn {gwBuildLayout:gwBuildLayout,gwSidBase:gwSidBase,gwIsBadSlot:gwIsBadSlot};")(
  function(id){return items[id]||null;},items);
const ctx=GB.context(items,stats);
const byGun={};Object.values(presets).forEach(p=>{(byGun[p.g]=byGun[p.g]||[]).push(p)});
function defInst(gid){const def=(stats.guns[gid]||{}).preset;const p=(def&&presets[def]&&presets[def].g===gid)?presets[def]:(byGun[gid]||[])[0];return (p&&p.i)||{};}
const gidOf=n=>Object.keys(items).find(k=>(items[k].n||"").indexOf(n)===0);

// 1) BAD
let badOk=0,badBad=[];
for(const gid of Object.keys(byGun)){
  const inst=defInst(gid);
  const tree=GB.buildTree(ctx,gid,inst);
  const L=api.gwBuildLayout({gunId:gid,installed:inst,slots:tree});
  L.cells.filter(c=>api.gwIsBadSlot(tree.nodes[c.path])).forEach(c=>{
    if(c.row===4&&c.col===6) badOk++; else badBad.push({gun:items[gid].n,path:c.path,r:c.row,c:c.col});
  });
}
console.log("BAD r4c6 ok:",badOk,"violations:",badBad.length,badBad.slice(0,3));

// 2) MPR45 chain upward same column
const mpr="5649a2464bdc2d91118b45a8";
let mprCases=[];
for(const gid of Object.keys(byGun)){
  const inst=defInst(gid);
  const tree=GB.buildTree(ctx,gid,inst);
  const mprSlot=Object.keys(tree.nodes).find(p=>(tree.nodes[p].allow||[]).includes(mpr));
  if(!mprSlot) continue;
  // install mpr and one child
  const t2=Object.assign({},inst,{[mprSlot]:mpr});
  const s2=GB.sanitize(ctx,gid,t2);
  const tree2=GB.buildTree(ctx,gid,s2.installed);
  const kids=(tree2.nodes[mprSlot]||{}).children||[];
  let inst3=Object.assign({},s2.installed);
  if(kids.length){const a0=(tree2.nodes[kids[0]].allow||[])[0]; if(a0) inst3[kids[0]]=a0;}
  const s3=GB.sanitize(ctx,gid,inst3);
  const L=api.gwBuildLayout({gunId:gid,installed:s3.installed,slots:GB.buildTree(ctx,gid,s3.installed)});
  const byP={};L.cells.forEach(c=>byP[c.path]=c);
  const base=byP[mprSlot];
  if(!base) continue;
  const chain=L.cells.filter(c=>c.path.startsWith(mprSlot+"/")).map(c=>({p:c.path.split("/").pop(),r:c.row,c:c.col}));
  mprCases.push({gun:items[gid].n, rows:L.rows, topPad:L.topPad||0, mpr:{r:base.row,c:base.col}, chain});
}
console.log("\nMPR45 cases:",mprCases.length);
mprCases.slice(0,6).forEach(x=>console.log(" ",x.gun,"rows",x.rows,"pad",x.topPad,"mpr",JSON.stringify(x.mpr),"chain",JSON.stringify(x.chain)));

// 3) Nightforce Multimount
const multi="5aa66c72e5b5b00016327c93", atacr="5aa66be6e5b5b0214e506e97";
const gid=gidOf("SV-98 7.62x54R");
let inst=GB.sanitize(ctx,gid,defInst(gid)).installed;
delete inst["mod_sight_rear"]; inst["mod_scope"]=multi;
let s=GB.sanitize(ctx,gid,inst);
inst=Object.assign({},s.installed,{"mod_scope/mod_scope_000":atacr});
s=GB.sanitize(ctx,gid,inst);
const L=api.gwBuildLayout({gunId:gid,installed:s.installed,slots:GB.buildTree(ctx,gid,s.installed)});
console.log("\nMultimount rows",L.rows,"topPad",L.topPad,"exceptions",JSON.stringify(L.exceptions));
L.cells.forEach(c=>console.log("  ",c.path,"r"+c.row,"c"+c.col,c.lane));
