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
function defInst(gid){const st=(stats.guns||{})[gid]||{}; if(st.preset&&presets[st.preset]) return presets[st.preset].i||{}; return {};}
function base(s){return String(s||"").replace(/^mod_/,"").replace(/#\d+$/,"").replace(/_\d{3,}$/,"");}
let n=0;
for(const gid of Object.keys(gunslots)){
  const inst=GB.sanitize(ctx,gid,defInst(gid)).installed;
  const tree=GB.buildTree(ctx,gid,inst); const N=tree.nodes;
  const dv=Object.keys(N).filter(p=>{
    if(base(N[p].sid)!=="mount") return false;
    const par=N[p].parent; if(par && !/^(reciever|receiver|slide|frame|upper|lower)$/.test(base(N[par].sid))) return false;
    const allow=N[p].allow||[]; if(!allow.length) return false;
    return allow.some(a=>String((items[a]||{}).pt||"")==="Scope");
  });
  if(!dv.length) continue;
  n++;
  const rs=Object.keys(N).filter(p=>base(N[p].sid)==="sight_rear");
  const info=rs.map(p=>({p, kids:(N[p].children||[]).map(k=>base(N[k].sid)), allowN:(N[p].allow||[]).length}));
  console.log(items[gid].n.slice(0,26).padEnd(28),"dv",dv.length,"rs",JSON.stringify(info));
}
console.log("dovetail guns",n);
