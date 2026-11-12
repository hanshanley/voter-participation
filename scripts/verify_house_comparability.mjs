import assert from "node:assert/strict";
import {readFileSync,writeFileSync} from "node:fs";
import {resolve} from "node:path";
import {pathToFileURL} from "node:url";

const [website,results,proof]=process.argv.slice(2);
const api=await import(pathToFileURL(resolve(website,"public/scripts/participation-norc-house.js")));
const load=profile=>JSON.parse(readFileSync(resolve(results,`viewer-${profile}.json`)));
const baseline=load("original");
const receipt=JSON.parse(readFileSync(resolve(website,
  "data/participation-return-attribution/20261112-06/copula-receipt.json")));
let checks=0;
const held=new Set(["AK","AL","CA","FL","IL","KY","LA","MA","ME","MS","NC","NJ","NV","OK","TX","WA","WI"]);
for(const profile of ["original","attenuated","full"]){
  const data=load(profile);
  if(profile==="original") api.validateNorcFamilies(data);
  else api.validateNorcAssociation(data,baseline);
  for(const group of ["",...api.norcGroups(data.families.accepted_ridge_multinomial).map(value=>value.value)])
    for(const units of ["margin","democratic_two_party_share"]){
      api.norcSharedBound(data,group,units,receipt.shared_max_abs_margin[group]??null);checks++;
    }
  for(const [family,model] of Object.entries(data.families)){
    assert.equal(model.summary.return_anchored,33);
    for(const row of model.rows){
      assert.equal(row.source_comparison_available,!held.has(row.state_code));checks++;
      for(const group of ["",...api.norcGroups(model).map(value=>value.value)])
        for(const [view] of api.norcViews) for(const unit of ["margin","democratic_two_party_share"]){
          const value=api.norcMapValue(row,view,group,unit);
          if(held.has(row.state_code)) assert.equal(value,null);
          else if(value!==null) assert.ok(Number.isFinite(value));
          checks++;
        }
    }
  }
}
writeFileSync(proof,JSON.stringify({status:"passed_actual_reader_all_nine_models",
  checks,held_states:[...held],all_unqualified_behavioral_views_missing:true,
  source_only_scenarios_not_substituted:true},null,2)+"\n");
console.log(JSON.stringify({checks,status:"passed"}));
