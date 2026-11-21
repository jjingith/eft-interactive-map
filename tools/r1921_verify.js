const fs=require("fs"),path=require("path");
const ROOT=path.resolve(__dirname,"..");
const GB=require(path.join(ROOT,"gun_builder.js"));
const items=JSON.parse(fs.readFileSync(path.join(ROOT,"data/items.json"),"utf8")).items;
const stats=JSON.parse(fs.readFileSync(path.join(ROOT,"data/gun-stats.json"),"utf8"));
const presets=JSON.parse(fs.readFileSync(path.join(ROOT,"data/gun-presets.json"),"utf8")).presets||{};
const gunslots=JSON.parse(fs.readFileSync(path.join(ROOT,"data/gunslots.json"),"utf8")).guns;
const src=fs.readFileSync(path.join(ROOT,"app.js"),"utf8");
const block=src.slice(src.indexOf("function gwSidBase("),src.indexOf("function renderGunSkin("));
const api=new Function("itemRec","GW_ITEM_MAP",block+"\nreturn {gwBuildLayout:gwBuildLayout,gwSidBase:gwSidBase,gwSlotVisible:gwSlotVisible};")(function(id){return items[id]||null;},items);
const ctx=GB.context(items,stats);
const byGun={};Object.values(presets).forEach(p=>{(byGun[p.g]=byGun[p.g]||[]).push(p)});
function defInst(gid){const def=(stats.guns[gid]||{}).preset;const p=(def&&presets[def]&&presets[def].g===gid)?presets[def]:(byGun[gid]||[])[0];return (p&&p.i)||{};}
const bad={opticBelowBody:[],stockOffCol9:[],receiverUpperBad:[],receiverLowerBad:[],dupPath:[],overlap:[],outOfGrid:[]};
let n=0;
for(const gid of Object.keys(gunslots)){
  n++;
  const inst=GB.sanitize(ctx,gid,defInst(gid)).installed;
  const tree=GB.buildTree(ctx,gid,inst); const N=tree.nodes;
  const L=api.gwBuildLayout({gunId:gid,installed:inst,slots:tree});
  const pad=L.topPad||0, bodyRow=L.body.row;
  const seen={}, cellsSeen={};
  for(const c of L.cells){
    const b=api.gwSidBase(N[c.path].sid);
    if(seen[c.path]) bad.dupPath.push({gun:items[gid].n,path:c.path});
    seen[c.path]=1;
    if(cellsSeen[c.row+"|"+c.col]) bad.overlap.push({gun:items[gid].n,a:cellsSeen[c.row+"|"+c.col],b:c.path});
    cellsSeen[c.row+"|"+c.col]=c.path;
    if(c.row<1||c.row>L.rows||c.col<1||c.col>9) bad.outOfGrid.push({gun:items[gid].n,path:c.path,r:c.row,c:c.col});
    // 上置光学件不得低于本体行
    // 只审视"能装光学瞄具"的镜座/瞄具槽（子树含瞄具槽，或 allow 里的候选件自带瞄具槽）
    function subtreeHasScope(pp){const ks=(N[pp].children||[]);
      for(const k of ks){ if(api.gwSidBase(N[k].sid)==="scope") return true; if(subtreeHasScope(k)) return true;} return false;}
    function allowsOptic(pp){ for(const a of (N[pp].allow||[])){ const r=items[a]||{};
      for(const sl of (r.slots||[])) if(api.gwSidBase(sl.sid)==="scope") return true;} return false;}
    const isOptic=(b==="scope")||(b==="mount"&&(subtreeHasScope(c.path)||allowsOptic(c.path)));
    if(isOptic && c.row > bodyRow){
      // 豁免：护木/枪托等非机匣父件的顶盖类（父件本身就是下挂结构）
      const par=N[c.path].parent; const pb=par?api.gwSidBase(N[par].sid):"";
      if(!/^(handguard|hand_guard|stock)$/.test(pb))
        bad.opticBelowBody.push({gun:items[gid].n,path:c.path,base:b,row:c.row,bodyRow:bodyRow,parentBase:pb,item:(items[inst[c.path]]||{}).n||""});
    }
    if(b==="stock" && c.col!==9) bad.stockOffCol9.push({gun:items[gid].n,path:c.path,r:c.row,c:c.col});
  }
  const R=L.roles||{};
  if(R.receiverUpper){const c=L.cells.find(x=>x.path===R.receiverUpper);
    if(!c||c.row!==bodyRow||c.col!==L.body.col-1) bad.receiverUpperBad.push({gun:items[gid].n,c:c&&{r:c.row,c:c.col}});}
  if(R.receiverLower){const u=L.cells.find(x=>x.path===R.receiverUpper), l=L.cells.find(x=>x.path===R.receiverLower);
    if(!l||!u||l.col!==u.col||l.row!==u.row+1) bad.receiverLowerBad.push({gun:items[gid].n,l:l&&{r:l.row,c:l.col},u:u&&{r:u.row,c:u.col}});}
}
console.log("guns",n);
for(const k of Object.keys(bad)) console.log(k, bad[k].length, JSON.stringify(bad[k].slice(0,3)));
