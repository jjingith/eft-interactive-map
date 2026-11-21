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
function defInst(gid){const def=(stats.guns[gid]||{}).preset;const p=(def&&presets[def]&&presets[def].g===gid)?presets[def]:(byGun[gid]||[])[0];return (p&&p.i)||{};}
const needle=process.argv[2]||"SV-98";
const gid=Object.keys(byGun).find(k=>((items[k]||{}).n||"").indexOf(needle)>=0);
const inst=GB.sanitize(ctx,gid,defInst(gid)).installed;
const L=api.gwBuildLayout({gunId:gid,installed:inst,slots:GB.buildTree(ctx,gid,inst)});
console.log(items[gid].n,'body',JSON.stringify(L.body));
L.cells.filter(c=>c.row===L.body.row).forEach(c=>console.log(' r'+c.row+'c'+c.col,'lane='+c.lane,c.path));
console.log('exceptions',JSON.stringify(L.exceptions,null,1));
