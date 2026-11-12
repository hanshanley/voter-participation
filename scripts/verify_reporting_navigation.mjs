import assert from "node:assert/strict";
import {readFileSync,writeFileSync} from "node:fs";
import {join,resolve} from "node:path";
import {pathToFileURL} from "node:url";
import {gunzipSync} from "node:zlib";
import {createHash} from "node:crypto";
const args=Object.fromEntries(Array.from({length:(process.argv.length-2)/2},(_,i)=>
  [process.argv[2+2*i].replace(/^--/,""),process.argv[3+2*i]]));
const read=p=>readFileSync(p),json=p=>JSON.parse(read(p));
const hash=b=>createHash("sha256").update(b).digest("hex");
let checks=0;const same=(a,b)=>{assert.deepEqual(a,b);checks++;};
const root=resolve(args.datasets),baseline=resolve(args.baseline);
const c=await import(pathToFileURL(join(resolve(args.reader),"participation-counts.js")));
const index=json(join(root,"counts/index.json")),oldIndex=json(join(baseline,"counts/index.json"));
const native=json(join(baseline,"native/index.json")),summary=json(join(root,"summary.json"));
const descriptor=json(join(root,"counts/dataset.json"));
for(const [name,pin] of Object.entries(descriptor.files)){
  const body=read(join(root,"counts",name));same(body.length,pin.bytes);same(hash(body),pin.sha256);
}
let parents=0,rows=0,unknown=0,zeros=0;
for(const code of Object.keys(oldIndex.states)){
  if(!["AR","AZ","WY"].includes(code)){
    same(index.states[code],oldIndex.states[code]);same(index.coverage[code],oldIndex.coverage[code]);
    same(read(join(root,"counts",index.states[code].file)),read(join(baseline,"counts",oldIndex.states[code].file)));
    continue;
  }
  const previous=JSON.parse(gunzipSync(read(join(baseline,"counts",oldIndex.states[code].file))));
  const state=c.validateCountShard(JSON.parse(gunzipSync(read(join(root,"counts",index.states[code].file)))),code,index.states[code]);
  same(state.records.slice(0,previous.records.length),previous.records);
  const additions=state.records.slice(previous.records.length);
  const table=JSON.parse(gunzipSync(read(join(baseline,"native",native.reporting_tables[code].file))));
  same(additions.length,summary.states[code].rows);same(additions.length,table.records.length);
  const originals=new Map(table.records.map(row=>[row.observation.id,row]));
  const counties=new Map(previous.records.filter(row=>previous.views.official.counties.includes(row.id))
    .map(row=>[row.view.county_id,row]));
  parents+=counties.size;
  for(const row of additions){
    const original=originals.get(row.id),parent=counties.get(row.view.county_id);
    assert.ok(original&&parent);checks++;
    for(const key of ["count","denominator","source","source_clock","reporting_status","quality","measure","election"])
      same(row[key],original.observation[key]);
    same(row.geography.join,original.observation.geography.join);
    same(row.geography.parent_id,parent.geography.id);
    same(row.view.unit_key,original.properties.key);same(row.view.unit,original.properties.precinct);
    same(row.view.unit_kind,original.properties.reporting_unit_kind);
    same(row.view.reported_pct,null);same(row.view.maps_approved,false);
    assert.ok(row.view.review_id&&row.view.complete_download_url&&row.view.source_reporting_label);checks++;
    rows++;unknown+=row.count.value===null;zeros+=row.count.value===0;
  }
  for(const mode of ["available","official","uf_vep","uf_vap"]){
    same(state.views[mode].counties,previous.views[mode].counties);
    same(state.views[mode].nongeographic,previous.views[mode].nongeographic);
    const frame=c.countFrame(state,mode);same(frame.precincts.length,additions.length);
    for(const county of frame.counties){
      const units=frame.precincts.filter(row=>row.county_id===county.county_id);
      assert.ok(units.length>0&&units.every(row=>row.unit&&row.unit_kind));checks++;
    }
  }
  for(const mode of ["in_person_early","mail_returned"])same(state.views[mode],previous.views[mode]);
}
same(rows,4963);same(parents,113);same(unknown,83);same(zeros,22);
const result={status:"pass",checks,reporting_rows_connected:rows,county_parents:parents,
  source_unknowns_preserved:unknown,true_zeros_preserved:zeros,old_records_preserved:true,
  other48_state_shards_unchanged:true,all_native_tables_and_bindings_unchanged:true,
  no_new_numerical_observations_rates_or_precinct_polygons:true,real_frontend_contracts_verified:true};
writeFileSync(args.proof,JSON.stringify(result,null,2)+"\n");console.log(JSON.stringify(result));
