import { useState } from 'react';
import { api, type Spec, type SpecColumn, type SpecTable } from './api';
import { Card, Notice } from './components';

const proposed = {origin:'user',detail:'Declared in the dataset editor',confirmed:true};
const idColumn = (name='id'): SpecColumn => ({name,type:'integer',role:'identifier',nullable:false,provenance:proposed});
export const newTable = (name='records'): SpecTable => ({name,rows:100,primary_key:'id',unique_keys:[],columns:[idColumn()],constraints:[],source:{kind:'none'}});
export function blankSpec(): Spec {
  return {spec_version:'2.0',name:'My dataset',mode:'schema_rules',purpose:'software_testing',engine:'rules',seed:2026,tables:[newTable()],relationships:[],privacy:{mechanism:'none',release_claim_permitted:false},evaluation:{checks:['schema','constraints']}};
}
export function downloadSpec(spec: Spec) {
  const url=URL.createObjectURL(new Blob([JSON.stringify(spec,null,2)],{type:'application/json'}));
  const a=document.createElement('a'); a.href=url; a.download='specification.json'; a.click(); URL.revokeObjectURL(url);
}

type Rule = {kind?:string;start?:number|string;end?:number|string;values?:unknown[];provider?:string};
export function SpecEditor({spec,onApply,onDirty}:{spec:Spec;onApply:(s:Spec)=>Promise<void>;onDirty:(dirty:boolean)=>void}) {
  const [draft,setDraft]=useState<Spec>(()=>structuredClone(spec));
  const [advanced,setAdvanced]=useState(false);
  const [raw,setRaw]=useState(JSON.stringify(spec,null,2));
  const [error,setError]=useState('');
  const [dirty,setDirty]=useState(false);
  const [busy,setBusy]=useState(false);
  function update(next:Spec){setDraft(next);setDirty(true);onDirty(true);setError('');}
  function tableChange(i:number, changes:Partial<SpecTable>){update({...draft,tables:draft.tables.map((t,j)=>j===i?{...t,...changes}:t)});}
  function columnChange(ti:number,ci:number,changes:Partial<SpecColumn>){tableChange(ti,{columns:draft.tables[ti].columns.map((c,j)=>j===ci?{...c,...changes,provenance:proposed}:c)});}
  async function apply(){
    setBusy(true);setError('');
    try {
      const next=advanced?JSON.parse(raw) as Spec:draft;
      const result=await api.validate(next);
      if(!result.ok){setError(result.findings.filter(f=>f.severity==='error').map(f=>`${f.scope}: ${f.message}`).join('\n'));return;}
      await onApply(next);setDraft(next);setDirty(false);onDirty(false);
    } catch(e){setError(String(e));} finally{setBusy(false);}
  }
  function addRelationship(){
    const parent=draft.tables[0],child=draft.tables[1];
    const pk=parent.primary_key??parent.columns[0].name;
    const key=`${parent.name}_${pk}`;
    const tables=draft.tables.map((t,i)=>i===1?{...t,rows:null,columns:t.columns.some(c=>c.name===key)?t.columns:[...t.columns,{name:key,type:parent.columns.find(c=>c.name===pk)?.type??'integer',role:'rule',rule:{kind:'sequence'},provenance:proposed}]}:t);
    update({...draft,tables,relationships:[...draft.relationships,{parent_table:parent.name,parent_key:pk,child_table:child.name,child_key:key,cardinality:'one_to_many',child_count_min:1,child_count_max:5,optional:false,null_fraction:0}]});
  }
  return <Card title="Design your dataset" sub="One table represents one kind of record. Your choices remain editable before generation.">
    <div className="row" style={{marginBottom:16}}>
      <button aria-pressed={!advanced} onClick={()=>{if(advanced&&dirty){setError('Apply or discard JSON changes before switching.');return;}setAdvanced(false);}}>Guided editor</button>
      <button aria-pressed={advanced} onClick={()=>{setRaw(JSON.stringify(draft,null,2));setAdvanced(true);}}>Advanced JSON</button>
      <button onClick={()=>downloadSpec(draft)}>Export specification</button>
    </div>
    {advanced?<label className="stack">Specification JSON<textarea className="json-editor" rows={18} value={raw} onChange={e=>{setRaw(e.target.value);setDirty(true);onDirty(true);}} spellCheck={false}/></label>:<>
      <div className="grid grid-3 editor-fields">
        <label>Dataset name<input value={draft.name} onChange={e=>update({...draft,name:e.target.value})}/></label>
        <label>What will you use it for?<select value={draft.purpose} onChange={e=>update({...draft,purpose:e.target.value})}>{[['software_testing','Testing software'],['teaching','Teaching and practice'],['analytics','Exploring analysis'],['ml_development','Developing an ML model'],['scenario_simulation','Simulating a scenario']].map(([v,l])=><option key={v} value={v}>{l}</option>)}</select></label>
        <label>Protected entity (if learning)<input placeholder="For example: customer or employee" value={draft.privacy.protected_entity??''} onChange={e=>update({...draft,privacy:{...draft.privacy,protected_entity:e.target.value||null}})}/></label>
      </div>
      {draft.tables.map((t,ti)=><fieldset className="editor-table" key={ti}><legend>Table {ti+1}: {t.name}</legend>
        <div className="grid grid-3 editor-fields">
          <label>Table name<input value={t.name} onChange={e=>tableChange(ti,{name:e.target.value})}/></label>
          <label>Rows {draft.relationships.some(r=>r.child_table===t.name)?'(leave blank to use relationships)':''}<input type="number" min={0} max={200000} value={t.rows??''} onChange={e=>tableChange(ti,{rows:e.target.value===''?null:Number(e.target.value)})}/></label>
          <label>Unique record identifier<select value={t.primary_key??''} onChange={e=>tableChange(ti,{primary_key:e.target.value||null})}><option value="">None</option>{t.columns.filter(c=>c.role==='identifier').map(c=><option key={c.name}>{c.name}</option>)}</select></label>
        </div>
        {t.columns.map((c,ci)=>{
          const rule=(c.rule??{}) as Rule;
          const chooseType=(type:string)=>columnChange(ti,ci,{type,role:'rule',rule:type==='category'?{kind:'choice',values:['A','B']}:type==='boolean'?{kind:'choice',values:[true,false]}:type==='string'?{kind:'faker',provider:'word'}:type==='date'||type==='timestamp'?{kind:type==='date'?'date_range':'timestamp_range',start:'2026-01-01',end:'2026-12-31'}:{kind:type==='integer'?'integer_range':'number_range',start:0,end:100}});
          return <div className="column-editor" key={ci}>
            <div className="grid grid-3 editor-fields">
              <label>Column name<input aria-label={`Table ${ti+1} column ${ci+1} name`} value={c.name} onChange={e=>columnChange(ti,ci,{name:e.target.value})}/></label>
              <label>Data type<select value={c.type} onChange={e=>chooseType(e.target.value)}>{['integer','number','category','string','boolean','date','timestamp','uuid'].map(v=><option key={v}>{v}</option>)}</select></label>
              <label>How to create values<select value={c.role} onChange={e=>{
                const role=e.target.value;
                columnChange(ti,ci,{role,...(role==='rule'&&!c.rule?{rule:{kind:'integer_range',start:0,end:100}}:{}),...(role==='derived'&&!c.formula?{formula:{op:'mul',args:[{col:t.columns.find(x=>x.name!==c.name)?.name??'choose_column'},{const:1}]}}:{}),...(role==='constant'?{constant_value:c.type==='boolean'?false:c.type==='string'?'example':0}:{}),...(role==='empty'?{nullable:true}:{})});
              }}>{[['identifier','New unique identifier'],['rule','My declared rule'],...(t.source.kind!=='none'?[['learned','Learn from uploaded data']]:[]),['constant','Always the same value'],['empty','Always empty'],['derived','Calculate using a formula'],...(c.role==='aggregate'?[['aggregate','Summarize related records']]:[])].map(([v,l])=><option key={v} value={v}>{l}</option>)}</select></label>
            </div>
            {c.role==='rule'&&<div className="grid grid-3 editor-fields">
              <label>Generation rule<select value={rule.kind??'integer_range'} onChange={e=>columnChange(ti,ci,{rule:{kind:e.target.value,start:0,end:100,values:['A','B'],provider:'word'}})}>{['integer_range','number_range','choice','faker','sequence','uuid4','date_range','timestamp_range'].map(v=><option key={v}>{v}</option>)}</select></label>
              {['integer_range','number_range','date_range','timestamp_range'].includes(rule.kind??'')&&<><label>From<input value={rule.start??''} onChange={e=>columnChange(ti,ci,{rule:{...rule,start:rule.kind?.includes('range')&&!rule.kind?.includes('date')&&!rule.kind?.includes('timestamp')?Number(e.target.value):e.target.value}})}/></label><label>To<input value={rule.end??''} onChange={e=>columnChange(ti,ci,{rule:{...rule,end:rule.kind?.includes('range')&&!rule.kind?.includes('date')&&!rule.kind?.includes('timestamp')?Number(e.target.value):e.target.value}})}/></label></>}
              {rule.kind==='choice'&&<label>Choices, separated by commas<input value={(rule.values??[]).join(', ')} onChange={e=>columnChange(ti,ci,{rule:{...rule,values:e.target.value.split(',').map(v=>c.type==='boolean'?v.trim()==='true':c.type==='integer'||c.type==='number'?Number(v):v.trim())}})}/></label>}
              {rule.kind==='faker'&&<label>Example provider<select value={rule.provider??'word'} onChange={e=>columnChange(ti,ci,{rule:{...rule,provider:e.target.value}})}>{['word','name','email','company','city','country'].map(v=><option key={v}>{v}</option>)}</select></label>}
            </div>}
            {c.role==='constant'&&<label className="stack">Constant value<input value={String(c.constant_value??'')} onChange={e=>columnChange(ti,ci,{constant_value:c.type==='number'||c.type==='integer'?Number(e.target.value):c.type==='boolean'?e.target.value==='true':e.target.value})}/></label>}
            {c.role==='derived'&&<><p className="small secondary">{c.description||'Computed from other columns.'} You can replace the formula below or edit the full expression in Advanced JSON.</p><FormulaEditor columns={t.columns.filter(x=>x.name!==c.name)} onSet={formula=>columnChange(ti,ci,{formula})}/></>}
            <div className="row"><label><input type="checkbox" checked={c.nullable??false} onChange={e=>columnChange(ti,ci,{nullable:e.target.checked,null_fraction:e.target.checked?(c.null_fraction??0):0})}/> Allow missing values</label><button className="ghost" onClick={()=>tableChange(ti,{columns:t.columns.filter((_,j)=>j!==ci)})}>Remove {c.name||'column'}</button></div>
          </div>;
        })}
        <div className="row"><button onClick={()=>tableChange(ti,{columns:[...t.columns,{name:`field_${t.columns.length+1}`,type:'integer',role:'rule',rule:{kind:'integer_range',start:0,end:100},provenance:proposed}]})}>Add column to {t.name}</button>{draft.tables.length>1&&<button onClick={()=>update({...draft,tables:draft.tables.filter((_,i)=>i!==ti),relationships:draft.relationships.filter(r=>r.parent_table!==t.name&&r.child_table!==t.name)})}>Remove table</button>}</div>
      </fieldset>)}
      {draft.mode!=='learned_table'&&<button onClick={()=>update({...draft,mode:'relational_rules',engine:'relational_rules',tables:[...draft.tables,newTable(`table_${draft.tables.length+1}`)]})}>Add another table</button>}
      {draft.tables.length>1&&<fieldset className="editor-table"><legend>Link your tables</legend><p className="small secondary">A parent record can have several child records. Links use the parent’s unique identifier. For a junction table, connect both parents.</p>
        {draft.relationships.map((r,i)=><div className="column-editor" key={i}><div className="grid grid-3 editor-fields">
          <label>Parent table<select value={r.parent_table} onChange={e=>{const t=draft.tables.find(t=>t.name===e.target.value)!;const pk=t.primary_key??t.columns[0].name;const fk=`${t.name}_${pk}`;const tables=draft.tables.map(child=>child.name===r.child_table&&!child.columns.some(c=>c.name===fk)?{...child,columns:[...child.columns,{name:fk,type:t.columns.find(c=>c.name===pk)?.type??'integer',role:'rule',rule:{kind:'sequence'},provenance:proposed}]}:child);update({...draft,tables,relationships:draft.relationships.map((x,j)=>j===i?{...x,parent_table:t.name,parent_key:pk,child_key:fk}:x)});}}>{draft.tables.map(t=><option key={t.name}>{t.name}</option>)}</select></label>
          <label>Child table<select value={r.child_table} onChange={e=>update({...draft,relationships:draft.relationships.map((x,j)=>j===i?{...x,child_table:e.target.value,child_key:draft.tables.find(t=>t.name===e.target.value)?.columns.find(c=>c.role!=='identifier')?.name??''}:x)})}>{draft.tables.map(t=><option key={t.name}>{t.name}</option>)}</select></label>
          <label>Child link column<select value={r.child_key} onChange={e=>update({...draft,relationships:draft.relationships.map((x,j)=>j===i?{...x,child_key:e.target.value}:x)})}><option value="">Choose a column</option>{draft.tables.find(t=>t.name===r.child_table)?.columns.map(c=><option key={c.name}>{c.name}</option>)}</select></label>
          <label>Relationship<select value={r.cardinality} onChange={e=>update({...draft,relationships:draft.relationships.map((x,j)=>j===i?{...x,cardinality:e.target.value,...(e.target.value==='one_to_one'?{child_count_min:0,child_count_max:1}:{})}:x)})}><option value="one_to_many">One parent, many children</option><option value="one_to_one">At most one child per parent</option></select></label>
          {(['child_count_min','child_count_max'] as const).map((key,k)=><label key={key}>{k?'Maximum':'Minimum'} children per parent<input type="number" min={0} value={r[key]??''} onChange={e=>update({...draft,relationships:draft.relationships.map((x,j)=>j===i?{...x,[key]:e.target.value===''?null:Number(e.target.value)}:x)})}/></label>)}
        </div><div className="row"><label><input type="checkbox" checked={r.optional??false} onChange={e=>update({...draft,tables:draft.tables.map(t=>t.name===r.child_table?{...t,columns:t.columns.map(c=>c.name===r.child_key?{...c,nullable:e.target.checked}:c)}:t),relationships:draft.relationships.map((x,j)=>j===i?{...x,optional:e.target.checked,null_fraction:0}:x)})}/>Allow a child without a parent</label>{r.optional&&<label>Fraction of unlinked children<input type="number" min={0} max={0.99} step={0.01} value={r.null_fraction??0} onChange={e=>update({...draft,relationships:draft.relationships.map((x,j)=>j===i?{...x,null_fraction:Number(e.target.value)}:x)})}/></label>}<button onClick={()=>update({...draft,relationships:draft.relationships.filter((_,j)=>j!==i)})}>Remove link</button></div></div>)}
        <button onClick={addRelationship}>Add relationship</button>
        {draft.tables.map(t=>{const incoming=draft.relationships.filter(r=>r.child_table===t.name);if(incoming.length!==2)return null;const keys=incoming.map(r=>r.child_key);return <label className="row" key={t.name}><input type="checkbox" checked={(t.unique_keys??[]).some(k=>keys.every(v=>k.includes(v)))} onChange={e=>tableChange(draft.tables.indexOf(t),{unique_keys:e.target.checked?[...(t.unique_keys??[]),keys]:(t.unique_keys??[]).filter(k=>!keys.every(v=>k.includes(v)))})}/>Each parent pair appears once in {t.name}</label>;})}
      </fieldset>}
    </>}
    {error&&<Notice tone="critical" title="Check these details"><span style={{whiteSpace:'pre-wrap'}}>{error}</span></Notice>}
    <div className="row" style={{marginTop:16}}><button className="primary" onClick={()=>void apply()} disabled={busy}>{busy?'Checking…':'Apply and validate changes'}</button>{dirty&&<><span role="status">Unsaved changes — apply before generating.</span><button onClick={()=>{setDraft(structuredClone(spec));setRaw(JSON.stringify(spec,null,2));setDirty(false);onDirty(false);setError('');}}>Discard edits</button></>}</div>
  </Card>;
}

function FormulaEditor({columns,onSet}:{columns:SpecColumn[];onSet:(formula:unknown)=>void}){
 const [left,setLeft]=useState(columns[0]?.name??'');const [right,setRight]=useState(columns[1]?.name??columns[0]?.name??'');const [op,setOp]=useState('mul');
 return <div className="row"><label>First column<select value={left} onChange={e=>setLeft(e.target.value)}>{columns.map(c=><option key={c.name}>{c.name}</option>)}</select></label><label>Operation<select value={op} onChange={e=>setOp(e.target.value)}>{[['mul','Multiply'],['add','Add'],['sub','Subtract'],['div','Divide'],['gt','Greater than'],['duration_hours','Elapsed hours']].map(([v,l])=><option key={v} value={v}>{l}</option>)}</select></label><label>Second column<select value={right} onChange={e=>setRight(e.target.value)}>{columns.map(c=><option key={c.name}>{c.name}</option>)}</select></label><button disabled={!left||!right} onClick={()=>onSet({op,args:[{col:left},{col:right}]})}>Use this formula</button></div>;
}
