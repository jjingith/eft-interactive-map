const fs=require("fs"),path=require("path");
const ROOT=path.resolve(__dirname,"..");
const GB=require(path.join(ROOT,"gun_builder.js"));
const items=JSON.parse(fs.readFileSync(path.join(ROOT,"data/items.json"),"utf8")).items;
const stats=JSON.parse(fs.readFileSync(path.join(ROOT,"data/gun-stats.json"),"utf8"));
const presets=JSON.parse(fs.readFileSync(path.join(ROOT,"data/gun-presets.json"),"utf8")).presets||{};
const gunslots=JSON.parse(fs.readFileSync(path.join(ROOT,"data/gunslots.json"),"utf8")).guns;
const ctx=GB.context(items,stats);
const byGun={};Object.values(presets).forEach(p=>{(byGun[p.g]=byGun[p.g]||[]).push(p)});
function defInst(gid){const def=(stats.guns[gid]||{}).preset;const p=(def&&presets[def]&&presets[def].g===gid)?presets[def]:(byGun[gid]||[])[0];return (p&&p.i)||{};}
function base(sid){return String(sid||"").replace(/^mod_/,"").replace(/#\d+$/,"").replace(/_\d{3,}$/,"");}
const REC=/^(reciever|receiver|slide|frame|upper|lower)$/;
const out={nestedReceiver:[],stockUnderNonRoot:[],mountWithScope:[],gunCount:0};
for(const gid of Object.keys(gunslots)){
  out.gunCount++;
  const inst=GB.sanitize(ctx,gid,defInst(gid)).installed;
  const tree=GB.buildTree(ctx,gid,inst);
  const N=tree.nodes;
  for(const p of Object.keys(N)){
    const n=N[p], b=base(n.sid);
    const pn=n.parent?N[n.parent]:null, pb=pn?base(pn.sid):"";
    if(REC.test(b) && REC.test(pb) && n.parent){
      out.nestedReceiver.push({gun:items[gid].n,gid,path:p,sid:n.sid,parent:n.parent,parentSid:pn.sid,
        item:(items[inst[p]]||{}).n||"", parentItem:(items[inst[n.parent]]||{}).n||""});
    }
    if(b==="stock" && n.parent && !REC.test(pb) && pb!=="stock"){
      out.stockUnderNonRoot.push({gun:items[gid].n,gid,path:p,parent:n.parent,parentBase:pb,
        item:(items[inst[p]]||{}).n||"", parentItem:(items[inst[n.parent]]||{}).n||""});
    }
    if(b==="mount" && (n.children||[]).some(k=>base(N[k].sid)==="scope")){
      const sc=(n.children||[]).filter(k=>base(N[k].sid)==="scope")[0];
      out.mountWithScope.push({gun:items[gid].n,gid,path:p,parentBase:pb,
        item:(items[inst[p]]||{}).n||"", scopeAllowFirst:(N[sc].allow||[]).slice(0,1).map(a=>(items[a]||{}).n)});
    }
  }
}
console.log("guns",out.gunCount);
console.log("\n=== nested receiver under receiver:",out.nestedReceiver.length);
out.nestedReceiver.forEach(x=>console.log(" ",x.gun,"|",x.sid,"under",x.parentSid,"| item",x.item,"| parentItem",x.parentItem));
console.log("\n=== stock under non-root(non-stock) parent:",out.stockUnderNonRoot.length);
out.stockUnderNonRoot.slice(0,20).forEach(x=>console.log(" ",x.gun,"|",x.path,"| parentBase",x.parentBase,"| item",x.item,"| parentItem",x.parentItem));
console.log("\n=== mount with scope child:",out.mountWithScope.length);
out.mountWithScope.slice(0,20).forEach(x=>console.log(" ",x.gun,"|",x.path,"| parentBase",x.parentBase,"| item",x.item));
