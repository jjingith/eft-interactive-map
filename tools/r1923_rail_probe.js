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
let n=0, free2c5=0;
for(const gid of Object.keys(gunslots)){
  const inst=GB.sanitize(ctx,gid,defInst(gid)).installed;
  const tree=GB.buildTree(ctx,gid,inst); const N=tree.nodes;
  const L=api.gwBuildLayout({gunId:gid,installed:inst,slots:tree});
  const recMounts=L.cells.filter(c=>{
    const b=api.gwSidBase(N[c.path].sid);
    if(b!=="mount") return false;
    const par=N[c.path].parent; if(!par) return false;
    return /^(reciever|receiver)$/.test(api.gwSidBase(N[par].sid));
  });
  if(!recMounts.length) continue;
  n++;
  const at2c5=L.cells.filter(c=>c.row===2&&c.col===5);
  if(!at2c5.length) free2c5++;
  console.log(items[gid].n.slice(0,26).padEnd(28),"mounts",recMounts.map(c=>c.row+"c"+c.col).join(","),
    "| r2c5:",at2c5.map(c=>api.gwSidBase(N[c.path].sid)+":"+c.path.slice(-18)).join("|")||"(free)",
    "| scopeAnchor:", L.row2 && L.row2.scope ? "yes":"no");
}
console.log("guns with receiver mounts:",n,"r2c5 free:",free2c5);
