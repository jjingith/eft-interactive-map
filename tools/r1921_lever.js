const fs=require("fs"),path=require("path");
const ROOT=path.resolve(__dirname,"..");
const GB=require(path.join(ROOT,"gun_builder.js"));
const items=JSON.parse(fs.readFileSync(path.join(ROOT,"data/items.json"),"utf8")).items;
const stats=JSON.parse(fs.readFileSync(path.join(ROOT,"data/gun-stats.json"),"utf8"));
const gunslots=JSON.parse(fs.readFileSync(path.join(ROOT,"data/gunslots.json"),"utf8")).guns;
function base(sid){return String(sid||"").replace(/^mod_/,"").replace(/#\d+$/,"").replace(/_\d{3,}$/,"");}
const rows=[];
for(const gid of Object.keys(gunslots)){
  const it=items[gid]||{};
  const bases=(it.slots||[]).map(s=>base(s.sid));
  if(bases.includes("hammer")||bases.includes("trigger")){
    rows.push({gun:it.n,id:gid,hammer:bases.includes("hammer"),trigger:bases.includes("trigger"),
      charge:bases.includes("charge"),stock:bases.includes("stock"),grip:bases.includes("pistol_grip")||bases.includes("pistolgrip"),
      all:bases.join(",")});
  }
}
console.log("guns with hammer/trigger:",rows.length);
rows.forEach(r=>console.log(" ",r.gun.slice(0,34).padEnd(36),"hammer",r.hammer,"trigger",r.trigger,"charge",r.charge,"stock",r.stock,"grip",r.grip));
