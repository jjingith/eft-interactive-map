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
const rows=[];
for(const gid of Object.keys(gunslots)){
  const inst=GB.sanitize(ctx,gid,defInst(gid)).installed;
  const tree=GB.buildTree(ctx,gid,inst); const N=tree.nodes;
  const L=api.gwBuildLayout({gunId:gid,installed:inst,slots:tree});
  for(const c of L.cells){
    const b=api.gwSidBase(N[c.path].sid);
    if(!/^(mount|scope)$/.test(b)) continue;
    if(c.row<=L.body.row) continue;
    const par=N[c.path].parent; const pb=par?api.gwSidBase(N[par].sid):"(root)";
    rows.push({gun:items[gid].n,id:gid,slot:c.path,base:b,parentBase:pb,row:c.row,col:c.col,role:c.role||"",
      item:(items[inst[c.path]]||{}).n||""});
  }
}
console.log("below-body mount/scope cells:",rows.length);
const byParent={};
rows.forEach(r=>{(byParent[r.parentBase]=byParent[r.parentBase]||[]).push(r)});
for(const k of Object.keys(byParent)){
  console.log("== parent",k,byParent[k].length);
  byParent[k].slice(0,6).forEach(r=>console.log("   ",r.gun.slice(0,26).padEnd(28),r.base,r.row+"c"+r.col,r.slot.slice(-40)));
}
