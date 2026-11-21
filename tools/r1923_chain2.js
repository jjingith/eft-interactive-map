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
function defInst(gid){const st=(stats.guns||{})[gid]||{}; if(st.preset&&presets[st.preset]) return presets[st.preset].i||{}; return {};}
const gid=Object.keys(items).find(k=>(items[k].n||"").startsWith("AK-74N")&&items[k].pt==="Weapon");
const baseItem="591ee00d86f774592f7b841e";
let inst=GB.sanitize(ctx,gid,defInst(gid)).installed;
inst=Object.assign({},inst,{["mod_mount_000"]:baseItem});
let s=GB.sanitize(ctx,gid,inst);
// install scope on the base, then a side tactical
let tree=GB.buildTree(ctx,gid,s.installed);
const optSlot="mod_mount_000/mod_scope", sideSlot="mod_mount_000/mod_tactical";
const optAllow=(tree.nodes[optSlot].allow||[]);
const scopeItem=optAllow.find(a=>String((items[a]||{}).pt||"")==="Scope");
console.log("scope candidates",optAllow.length,"pick",(items[scopeItem]||{}).n);
if(scopeItem) s=GB.sanitize(ctx,gid,Object.assign({},s.installed,{[optSlot]:scopeItem}));
tree=GB.buildTree(ctx,gid,s.installed);
console.log("after scope:",Object.entries(s.installed).filter(([k])=>k.startsWith("mod_mount_000")).map(([k,v])=>k+"="+(items[v]||{}).n));
let L=api.gwBuildLayout({gunId:gid,installed:s.installed,slots:tree});
console.log("rows",L.rows,"pad",L.topPad);
L.cells.filter(c=>c.path.startsWith("mod_mount_000")||c.row<=2).sort((a,b)=>a.row-b.row||a.col-b.col)
 .forEach(c=>console.log(`  r${c.row}c${c.col} ${(c.role||c.lane).padEnd(14)} ${c.path} :: ${(items[s.installed[c.path]]||{}).n||""}`));
// remove base → chain disappears, rows shrink
let s2=GB.sanitize(ctx,gid,Object.assign({},GB.sanitize(ctx,gid,defInst(gid)).installed));
const L2=api.gwBuildLayout({gunId:gid,installed:s2.installed,slots:GB.buildTree(ctx,gid,s2.installed)});
console.log("after remove: rows",L2.rows,"pad",L2.topPad,"hasOptic",L2.cells.some(c=>c.role==="dovetailOptic"));
