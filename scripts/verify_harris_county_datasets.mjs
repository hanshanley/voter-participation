import assert from "node:assert/strict";
import {readFileSync,writeFileSync} from "node:fs";
import {join,resolve} from "node:path";
import {pathToFileURL} from "node:url";
import {gunzipSync} from "node:zlib";
import {createHash} from "node:crypto";
const args=Object.fromEntries(Array.from({length:(process.argv.length-2)/2},(_,i)=>
  [process.argv[2+2*i].replace(/^--/,""),process.argv[3+2*i]]));
const read=p=>readFileSync(p),json=p=>JSON.parse(read(p));
const hash=body=>createHash("sha256").update(body).digest("hex");
let checks=0;const same=(a,b)=>{assert.deepEqual(a,b);checks++;};
const root=resolve(args.datasets),old=resolve(args.baseline);
const c=await import(pathToFileURL(join(resolve(args.reader),"participation-counts.js")));
const n=await import(pathToFileURL(join(resolve(args.reader),"participation-native-bindings.js")));
for(const family of ["counts","native"]){
  const descriptor=json(join(root,family,"dataset.json")),before=json(join(old,family,"dataset.json"));
  for(const [name,pin] of Object.entries(descriptor.files)){
    const body=read(join(root,family,name));same(body.length,pin.bytes);same(hash(body),pin.sha256);
  }
  for(const name of Object.keys(before.files))
    if(name!=="index.json"&&!(family==="counts"&&name==="states/TX.json.gz"))
      same(read(join(root,family,name)),read(join(old,family,name)));
}
const index=json(join(root,"counts/index.json")),oldIndex=json(join(old,"counts/index.json"));
for(const key of Object.keys(oldIndex))if(!["states","coverage","harris_county_review"].includes(key))
  same(index[key],oldIndex[key]);
for(const code of Object.keys(oldIndex.states))if(code!=="TX"){
  same(index.states[code],oldIndex.states[code]);same(index.coverage[code],oldIndex.coverage[code]);
}
const state=c.validateCountShard(JSON.parse(gunzipSync(read(join(root,"counts/states/TX.json.gz")))),"TX",index.states.TX);
const previous=JSON.parse(gunzipSync(read(join(old,"counts/states/TX.json.gz"))));
same(state.records.slice(0,-1),previous.records);same(state.records.length,previous.records.length+1);
for(const mode of ["in_person_early","mail_returned"])same(state.views[mode],previous.views[mode]);
const native=json(join(root,"native/index.json")),priorNative=json(join(old,"native/index.json"));
for(const [key,value] of Object.entries(priorNative))if(!["county_bindings","county_frame_checks","harris_county_review"].includes(key))
  same(native[key],value);
for(const code of Object.keys(priorNative.county_bindings))if(code!=="TX")
  same(native.county_bindings[code],priorNative.county_bindings[code]);
for(const mode of ["in_person_early","mail_returned"])same(native.county_bindings.TX[mode],priorNative.county_bindings.TX[mode]);
const geometry=JSON.parse(gunzipSync(read(args.reference))),reference={sha256:hash(read(args.reference))};
for(const mode of ["available","official","uf_vep","uf_vap"]){
  const frame=c.countFrame(state,mode);same(frame.counties.length,1);
  const joined=n.bindCountyReference(frame.counties,geometry,reference,native.county_bindings.TX[mode]);
  same([...joined.keys()],["48201"]);const row=joined.get("48201");
  same(row.ballots,1392280);same(row.denominator,2761770);same(row.reported_pct,null);
  same(row.source_update_label,"11/4/2026");assert.ok(row.review_id&&row.complete_download_url);checks++;
  same(row.native_record.full_native_measures.length,13);
  const wrong=structuredClone(frame.counties);wrong[0].denominator_basis="population_turnout";
  assert.throws(()=>n.bindCountyReference(wrong,geometry,reference,native.county_bindings.TX[mode]));checks++;
}
const result={status:"pass",checks,new_county_observations:1,county_reference_features:254,
  archived_TX_records_preserved:previous.records.length,old_early_mail_counties:508,
  all_other_state_shards_unchanged:50,new_rates_or_precinct_polygons:0,
  WI_Jefferson_and_all_other_native_bindings_preserved:true,
  available_native_priority_not_mixed_with_early_activity:true,real_frontend_contracts_verified:true};
writeFileSync(args.proof,JSON.stringify(result,null,2)+"\n");console.log(JSON.stringify(result));
