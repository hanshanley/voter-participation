import assert from "node:assert/strict";
import {readFileSync,writeFileSync} from "node:fs";
import {resolve,join} from "node:path";
import {pathToFileURL} from "node:url";
import {gunzipSync} from "node:zlib";
import {createHash} from "node:crypto";

const args=Object.fromEntries(Array.from({length:(process.argv.length-2)/2},(_,i)=>
  [process.argv[2+2*i].replace(/^--/,""),process.argv[3+2*i]]));
const read=path=>readFileSync(path),json=path=>JSON.parse(read(path));
const hash=body=>createHash("sha256").update(body).digest("hex");
const counts=await import(pathToFileURL(join(resolve(args.reader),"participation-counts.js")));
const native=await import(pathToFileURL(join(resolve(args.reader),"participation-native-bindings.js")));
const root=resolve(args.datasets),oldCounts=resolve(args["old-counts"]),oldNative=resolve(args["old-native"]);
let checks=0;
const same=(a,b)=>{assert.deepEqual(a,b);checks++;};
for(const [family,old] of [["counts",oldCounts],["native",oldNative]]){
  const descriptor=json(join(root,family,"dataset.json")),previous=json(join(old,"dataset.json"));
  for(const [name,pin] of Object.entries(descriptor.files)){
    const body=read(join(root,family,name));same(body.length,pin.bytes);same(hash(body),pin.sha256);
  }
  for(const name of Object.keys(previous.files)){
    if(name==="index.json" || family==="counts"&&name==="states/WI.json.gz") continue;
    same(read(join(root,family,name)),read(join(old,name)));
  }
}
const index=json(join(root,"counts/index.json")),previousIndex=json(join(oldCounts,"index.json"));
for(const [key,value] of Object.entries(previousIndex))
  if(!["states","coverage","new_native_review"].includes(key)) same(index[key],value);
for(const [code,value] of Object.entries(previousIndex.states)) if(code!=="WI") same(index.states[code],value);
for(const [code,value] of Object.entries(previousIndex.coverage)) if(code!=="WI") same(index.coverage[code],value);
const data=counts.validateCountShard(JSON.parse(gunzipSync(read(join(root,"counts/states/WI.json.gz")))),"WI",index.states.WI);
const previous=JSON.parse(gunzipSync(read(join(oldCounts,"states/WI.json.gz"))));
same(data.records.slice(0,previous.records.length),previous.records);
same(data.records.length-previous.records.length,33);
for(const mode of ["in_person_early","mail_returned"]) same(data.views[mode],previous.views[mode]);
const ni=json(join(root,"native/index.json")),oi=json(join(oldNative,"index.json"));
for(const [key,value] of Object.entries(oi))
  if(!["county_bindings","reporting_tables","reporting_sources","additional_native_review","county_frame_checks"].includes(key))
    same(ni[key],value);
for(const [code,value] of Object.entries(oi.county_bindings)) if(code!=="WI") same(ni.county_bindings[code],value);
for(const mode of ["in_person_early","mail_returned"]) same(ni.county_bindings.WI[mode],oi.county_bindings.WI[mode]);
for(const key of ["reporting_tables","reporting_sources"])
  for(const [code,value] of Object.entries(oi[key])) if(code!=="WI") same(ni[key][code],value);
const geometry=JSON.parse(gunzipSync(read(args.reference))),sha=hash(read(args.reference));
for(const mode of ["available","official","uf_vep","uf_vap"]){
  const frame=counts.countFrame(data,mode);
  same(frame.counties.length,2);
  const joined=native.bindCountyReference(frame.counties,geometry,{sha256:sha},ni.county_bindings.WI[mode]);
  same([...joined.keys()].sort(),["55055","55105"]);
  const jefferson=joined.get("55055");
  same(jefferson.ballots,38414);same(jefferson.denominator,52428);
  assert.ok(Math.abs(jefferson.reported_pct-100*38414/52428)<1e-10);checks++;
  same(frame.precincts.length-previous.views[mode].precincts.length,32);
  const wrong=structuredClone(frame.counties);
  wrong.find(row=>row.county==="Jefferson County").county_fips="42065";
  assert.throws(()=>native.bindCountyReference(wrong,geometry,{sha256:sha},ni.county_bindings.WI[mode]));checks++;
}
const table=JSON.parse(gunzipSync(read(join(root,"native/tables/WI.json.gz"))));
same(table.records.length,32);
const names=new Set();
let ballots=0,registered=0,zeros=0;
for(const row of table.records){
  counts.validateCountObservation(row.observation,"WI");checks++;
  same(row.properties.ballots,row.observation.count.value);
  same(row.properties.reported_pct,null);
  same(row.observation.denominator.qualified,false);
  names.add(row.properties.precinct);
  ballots+=row.properties.ballots;registered+=row.properties.registered;zeros+=row.properties.ballots===0;
}
same(names.size,32);same(ballots,38414);same(registered,52428);same(zeros,1);
same(ni.reporting_tables.WI.coverage,{source_rows:32,fractions:0,reported:32,unknown:0,withheld:0});
const proof={status:"pass",checks,new_county_observations:1,new_reporting_unit_rows:32,
  unchanged_state_files:50,previous_WI_records_preserved:true,all_other_native_bindings_preserved:true,
  native_zeros_and_grouped_wards_preserved:true,new_precinct_polygons_or_population_claim:false,
  source_modes_preserved:true,actual_frontend_contracts_verified:true};
writeFileSync(args.proof,JSON.stringify(proof,null,2)+"\n");
console.log(JSON.stringify(proof));
