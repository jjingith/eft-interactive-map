const fs=require("fs"),path=require("path");
const ROOT=path.resolve(__dirname,"..");
const GB=require(path.join(ROOT,"gun_builder.js"));
const items=JSON.parse(fs.readFileSync(path.join(ROOT,"data/items.json"),"utf8")).items;
const stats=JSON.parse(fs.readFileSync(path.join(ROOT,"data/gun-stats.json"),"utf8"));
const presets=JSON.parse(fs.readFileSync(path.join(ROOT,"data/gun-presets.json"),"utf8")).presets||{};
const gunslots=JSON.parse(fs.readFileSync(path.join(ROOT,"data/gunslots.json"),"utf8")).guns;
const ctx=GB.context(items,stats);
function defInst(gid){const st=(stats.guns||{})[gid]||{}; if(st.preset&&presets[st.preset]) return presets[st.preset].i||{}; return {};}
function base(s){return String(s||"").replace(/^mod_/,"").replace(/#\d+$/,"").replace(/_\d{3,}$/,"");}
for(const gid of Object.keys(gunslots)){
  const inst=GB.sanitize(ctx,gid,defInst(gid)).installed;
  const tree=GB.buildTree(ctx,gid,inst); const N=tree.nodes;
  const dv=Object.keys(N).filter(p=>{
    if(base(N[p].sid)!=="mount") return false;
    const par=N[p].parent; if(par && !/^(reciever|receiver|slide|frame|upper|lower)$/.test(base(N[par].sid))) return false;
    const allow=N[p].allow||[]; if(!allow.length) return false;
    return allow.some(a=>String((items[a]||{}).pt||"")==="Scope");
  });
  if(dv.length<2) continue;
  console.log("==",items[gid].n);
  dv.forEach(p=>{
    const allow=N[p].allow||[];
    const scopes=allow.filter(a=>String((items[a]||{}).pt||"")==="Scope").map(a=>(items[a]||{}).n);
    console.log("  ",p,"| parent",N[p].parent||"(root)","| parentBase",N[p].parent?base(N[N[p].parent].sid):"-",
      "| allow",allow.length,"| scopes",scopes.length,scopes.slice(0,3).join(" / "),
      "| installed",(items[inst[p]]||{}).n||"");
  });
}
