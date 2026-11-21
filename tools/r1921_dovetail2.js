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
function defInst(gid){const st=(stats.guns||{})[gid]||{}; if(st.preset&&presets[st.preset]) return presets[st.preset].i||{};
  for(const pid in presets){const p=presets[pid]; if(p&&p.g===gid) return p.i||{};} return {};}
const gid=Object.keys(items).find(k=>(items[k].n||"").startsWith("AK-74N")&&items[k].pt==="Weapon");
let inst=GB.sanitize(ctx,gid,defInst(gid)).installed;
// 在燕尾槽槽位装 PSO-1
const tree0=GB.buildTree(ctx,gid,inst);
const dv=Object.keys(tree0.nodes).find(p=>{
  const a=tree0.nodes[p].allow||[];
  return a.some(x=>String((items[x]||{}).pt||"")==="Scope") && tree0.nodes[p].sid==="mod_mount_000";});
console.log("dovetail slot:",dv);
const pso=(tree0.nodes[dv].allow||[]).find(x=>(items[x]||{}).n==="BelOMO PSO-1 4x24 瞄准镜");
inst=Object.assign({},inst,{[dv]:pso});
const s=GB.sanitize(ctx,gid,inst);
console.log("installed pso:",s.installed[dv]===pso);
const tree=GB.buildTree(ctx,gid,s.installed);
const L=api.gwBuildLayout({gunId:gid,installed:s.installed,slots:tree});
L.cells.filter(c=>c.row<=2||c.path===dv||c.path.startsWith(dv)).forEach(c=>{
  console.log("  r"+c.row+"c"+c.col, c.role||c.lane, c.path, (items[s.installed[c.path]]||{}).n||"");
});
console.log("rows",L.rows,"pad",L.topPad);
