const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('collega_feedback_video.gs', 'utf8');
function scenario({missing=false, duplicate=false, title='Copia di Quiz', fail=false}={}) {
  let writes=0;
  const makeFeedback=(text,links)=>({getText:()=>text,getLinkUrls:()=>links});
  const items=[1,2].map(n=>({
    value:makeFeedback('Testo esistente',['https://example.org/risorsa']),
    getTitle:()=>n+'. Domanda '+n,getId:()=>n,
    getFeedbackForIncorrect(){return this.value;},
    setFeedbackForIncorrect(value){if(fail && this.getId()===2)throw Error('simulated');this.value=value;writes++;},
    asMultipleChoiceItem(){return this;}
  }));
  const doc={schema_version:1,title:'Quiz',questions:[1,2].map(n=>({question_number:n,title:'Domanda '+n,video_filename:'quiz_domanda_00'+n+'.mp4'}))};
  const folder={getName:()=> 'Feedback_Quiz', getFilesByName(name){
    const values=name==='feedback.json'?[{getBlob:()=>({getDataAsString:()=>JSON.stringify(doc)})}]:
      missing && name.includes('002')?[]:[{getUrl:()=> 'https://drive.google.com/file/d/'+name+'/view', getMimeType:()=> 'video/mp4'}];
    if(duplicate && name.includes('002'))values.push(values[0]);
    let i=0;return {hasNext:()=>i<values.length,next:()=>values[i++]};
  }};
  const context={console:{log(){}},Set, FormApp:{
    ItemType:{MULTIPLE_CHOICE:'MC'}, openById:()=>({isQuiz:()=>true,getTitle:()=>title,getItems:()=>items}),
    createFeedback(){let text='',links=[];return {setText(t){text=t;return this;},addLink(u){links.push(u);return this;},build(){return makeFeedback(text,links);}}}
  }, DriveApp:{getFolderById:()=>folder},LockService:{getScriptLock:()=>({waitLock(){},releaseLock(){}})}};
  vm.createContext(context);vm.runInContext(source,context);
  vm.runInContext("CONFIG_FEEDBACK.moduloUrl='https://docs.google.com/forms/d/form123/edit'; CONFIG_FEEDBACK.cartellaUrl='https://drive.google.com/drive/folders/folder123'",context);
  return {context,items,writes:()=>writes};
}
let s=scenario();s.context.verificaCollegamenti();assert.equal(s.writes(),0);
s.context.collegaVideoFeedback();s.context.collegaVideoFeedback();
assert.equal(s.items[0].value.getText(),'Testo esistente');assert.equal(s.items[0].value.getLinkUrls().length,2);
for(const options of [{missing:true},{duplicate:true},{title:'Altro quiz'}]){
 s=scenario(options);assert.throws(()=>s.context.collegaVideoFeedback());assert.equal(s.writes(),0);
}
s=scenario({fail:true});assert.throws(()=>s.context.collegaVideoFeedback());assert.equal(s.items[0].value.getLinkUrls().length,1);
assert.throws(()=>s.context.idGoogle_('https://docs.google.com/forms/d/e/published/viewform','moduloUrl'));
console.log('Apps Script: verifica, collegamento, riesecuzione, errori e ripristino OK');
