// 全枪械布局快照：真实槽位树 + 布局坐标 + 结构特征，用于修复前后对比
const fs=require("fs"),path=require("path");
const ROOT=path.resolve(__dirname,"..");
const GB=require(path.join(ROOT,"gun_builder.js"));
const items=JSON.parse(fs.readFileSync(path.join(ROOT,"data/items.json"),"utf8")).items;
const stats=JSON.parse(fs.readFileSync(path.join(ROOT,"data/gun-stats.json"),"utf8"));
const presets=JSON.parse(fs.readFileSync(path.join(ROOT,"data/gun-presets.json"),"utf8")).presets||{};
const gunslots=JSON.parse(fs.readFileSync(path.join(ROOT,"data/gunslots.json"),"utf8")).guns;
const APP=process.env.GW_APP||"app.js";
const src=fs.readFileSync(path.join(ROOT,APP),"utf8");
const block=src.slice(src.indexOf("function gwSidBase("),src.indexOf("function renderGunSkin("));
const api=new Function("itemRec","GW_ITEM_MAP",block+"\nreturn {gwBuildLayout:gwBuildLayout,gwSidBase:gwSidBase,gwLaneOf:gwLaneOf,gwSlotVisible:gwSlotVisible,gwMainRole:gwMainRole};")(function(id){return items[id]||null;},items);
const ctx=GB.context(items,stats);
const byGun={};Object.values(presets).forEach(p=>{(byGun[p.g]=byGun[p.g]||[]).push(p)});
function defInst(gid){
  // 与 app.js gunDefaultBuild() 完全一致：先看 gun-stats.preset 是否存在，再退回该枪第一个内置预设
  const st=(stats.guns||{})[gid]||{};
  if(st.preset && presets[st.preset]) return presets[st.preset].i||{};
  for(const pid in presets){const p=presets[pid]; if(p && p.g===gid) return p.i||{};}
  return {};
}
const out={generatedAt:new Date().toISOString(),guns:{}};
for(const gid of Object.keys(gunslots)){
  const inst=GB.sanitize(ctx,gid,defInst(gid)).installed;
  const tree=GB.buildTree(ctx,gid,inst);
  const L=api.gwBuildLayout({gunId:gid,installed:inst,slots:tree});
  out.guns[gid]={
    name:items[gid].n, rows:L.rows, topPad:L.topPad||0, body:L.body,
    cells:L.cells.map(c=>({path:c.path,slot:tree.nodes[c.path].sid,base:api.gwSidBase(tree.nodes[c.path].sid),
      lane:c.lane,row:c.row,col:c.col,parent:tree.nodes[c.path].parent||null,
      item:(items[inst[c.path]]||{}).n||"",anchorSlot:c.anchorSlot||null,role:c.role||null})),
    exceptions:L.exceptions
  };
}
const target=process.argv[2]||"docs/r19.15.1-layout-audit/_snapshot.json";
fs.writeFileSync(path.join(ROOT,target),JSON.stringify(out,null,1));
console.log("guns",Object.keys(out.guns).length,"->",target);
