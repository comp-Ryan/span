(function(){
  const pages=[["timeline","Timeline"],["questions","Questions"],["architecture","Architecture"],["spec","Spec"]];
  const here=location.pathname.replace("/","")||"timeline";
  const nav=document.createElement("nav");
  nav.innerHTML='<b>SPAN · hub</b>'+pages.map(([p,l])=>`<a href="/${p}" class="${p===here?'on':''}">${l}</a>`).join("")+'<span class="right" id="clock"></span>';
  document.body.prepend(nav);
  const dl=new Date("2026-10-18T12:00:00-07:00");
  function tick(){const now=new Date();const ms=dl-now;const h=Math.floor(ms/3.6e6),m=Math.floor(ms%3.6e6/6e4);
    document.getElementById("clock").textContent=now.toLocaleTimeString("en-US",{timeZone:"America/Los_Angeles",hour:"2-digit",minute:"2-digit"})+" PT · "+(ms>0?`${h}h ${m}m to submit`:"DEADLINE PASSED");}
  tick();setInterval(tick,30000);
})();
