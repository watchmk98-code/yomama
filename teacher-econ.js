/* Teacher-only live economy view. All values and actions come from the server.
   class.html drives it through window.TeacherEcon.start(teacher) / .stop() when
   the console logs in or leaves; on its own it starts from the stored login. */
(function(){
  'use strict';
  var root=document.getElementById('econ-teacher');if(!root)return;
  var esc=function(v){return String(v).replace(/[<>&"]/g,function(c){return {'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;'}[c];});};
  var money=function(v){var n=Number(v);return (n>=1000000?(n/1000000).toFixed(1)+'M':n>=10000?(n/1000).toFixed(1)+'k':n.toLocaleString('en-US'))+' YM';};
  var teacher=null,state=null,timer=null;
  function placeholder(){root.innerHTML='<h2>LIVE CLASS ECONOMY</h2><p>Open the console with your teacher code to view students and publish a market event.</p>';}
  function refresh(){
    if(!teacher)return Promise.resolve();
    return fetch('/api/game/teacher/econ?teacher_token='+encodeURIComponent(teacher.teacher_token)).then(function(r){return r.json().then(function(d){if(!r.ok)throw Error(d.error);return d;});}).then(function(d){
      state=d;
      if(!document.getElementById('econ-students')){
        root.innerHTML='<h2>LIVE CLASS ECONOMY · '+esc(d.code)+'</h2><div id="econ-students"></div><h3>CLASS NEWS EVENT</h3>'+
          '<form id="econ-chaos-form"><label>Headline <input name="headline" required maxlength="240"></label> '+
          '<label>Family <select name="family">'+Object.keys(d.families).map(function(f){return '<option value="'+esc(f)+'">'+esc(d.families[f].name)+'</option>';}).join('')+'</select></label> '+
          '<label>Direction <select name="direction"><option value="up">Up</option><option value="down">Down</option></select></label> '+
          '<label>Multiplier <input name="mag" type="number" step="any" value="'+d.eventDefaults.up+'" required></label> '+
          '<label>Hold minutes <input name="holdMin" type="number" step="any" value="'+d.eventDefaults.holdMin+'" required></label> '+
          '<button class="pill" type="submit">Publish event</button></form><p id="econ-teacher-message" role="status"></p>';
        var form=document.getElementById('econ-chaos-form');
        form.elements.direction.addEventListener('change',function(){form.elements.mag.value=state.eventDefaults[form.elements.direction.value];});
        form.addEventListener('submit',function(e){
          e.preventDefault();if(!teacher)return;var submit=form.querySelector('button');submit.disabled=true;
          var msg=document.getElementById('econ-teacher-message');
          fetch('/api/game/teacher/event',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({teacher_token:teacher.teacher_token,
            headline:form.elements.headline.value,family:form.elements.family.value,mag:Number(form.elements.mag.value),holdMin:Number(form.elements.holdMin.value)})})
            .then(function(r){return r.json().then(function(d){if(!r.ok)throw Error(d.error);return d;});})
            .then(function(){msg.textContent='Event published. Prices ramp up or down across the class.';return refresh();})
            .catch(function(e){msg.textContent=e.message;}).finally(function(){submit.disabled=false;});
        });
      }
      if(d.modelVersion===4){var eventForm=document.getElementById('econ-chaos-form');eventForm.hidden=true;eventForm.previousElementSibling.hidden=true;}
      document.getElementById('econ-students').innerHTML='<div class="data-table-wrap"><table class="data-table"><thead><tr><th>Student</th><th>Buildings</th><th>Families</th><th>Net worth</th><th>Checklist</th><th>Gate</th></tr></thead><tbody>'+
        d.students.map(function(p){var c=p.checklist;return '<tr><td>'+p.rank+'. '+esc(p.name)+'</td><td>'+p.buildings.map(function(b){return esc(b.name)+' Lv '+b.lv;}).join('<br>')+'</td><td>'+esc(Object.entries(p.families).map(function(x){return x.join(': ');}).join(', '))+'</td><td>'+money(p.netWorth)+'</td><td>'+[c.lv25?'✓ Level':'□ Level',c.auto?'✓ Customers':'□ Customers',c.goodSales+'/'+d.goodSalesNeeded+(d.modelVersion===4?' deliveries':' sales'),c.quiz?'✓ Quiz':'□ Quiz'].join(' · ')+'</td><td>'+(p.gateOpen?'Open':'Locked')+'</td></tr>';}).join('')+'</tbody></table></div>';
    }).catch(function(e){var msg=document.getElementById('econ-teacher-message');if(msg)msg.textContent=e.message;else root.textContent=e.message;});
  }
  function start(t){
    teacher=t;state=null;root.innerHTML='';
    if(timer)clearInterval(timer);
    timer=setInterval(function(){if(!document.hidden)refresh();},15000);
    return refresh();
  }
  function stop(){teacher=null;state=null;if(timer){clearInterval(timer);timer=null;}placeholder();}
  window.TeacherEcon={start:start,stop:stop};
  var stored=null;try{stored=JSON.parse(localStorage.getItem('yomama_teacher_v1')||'null');}catch(_){}
  if(stored&&stored.teacher_token)start(stored);else placeholder();
}());
