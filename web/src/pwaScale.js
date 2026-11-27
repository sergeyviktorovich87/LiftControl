// Only the installed app has a fixed application viewport. Browser tabs keep
// their normal zoom. OS accessibility tools may override page restrictions.
export function startPwaScaleLock(){
 const mode=window.matchMedia('(display-mode: standalone)');
 const fullscreen=window.matchMedia('(display-mode: fullscreen)');
 const viewport=document.querySelector('meta[name="viewport"]');
 const original=viewport?.getAttribute('content')||'width=device-width,initial-scale=1.0,interactive-widget=resizes-content';
 const installed=()=>mode.matches||fullscreen.matches||navigator.standalone===true;
 const apply=()=>{const enabled=installed();document.documentElement.classList.toggle('pwa-fixed-scale',enabled);if(viewport)viewport.setAttribute('content',enabled?original+',minimum-scale=1,maximum-scale=1,user-scalable=no':original);};
 const gesture=e=>{if(installed())e.preventDefault();};
 const wheel=e=>{if(installed()&&(e.ctrlKey||e.metaKey))e.preventDefault();};
 const key=e=>{if(installed()&&(e.ctrlKey||e.metaKey)&&['+','-','=','0','Add','Subtract'].includes(e.key))e.preventDefault();};
 apply();mode.addEventListener?.('change',apply);fullscreen.addEventListener?.('change',apply);window.addEventListener('pageshow',apply);
 for(const name of ['gesturestart','gesturechange','gestureend'])document.addEventListener(name,gesture,{passive:false});
 document.addEventListener('wheel',wheel,{passive:false});document.addEventListener('keydown',key);
 return()=>{mode.removeEventListener?.('change',apply);fullscreen.removeEventListener?.('change',apply);window.removeEventListener('pageshow',apply);for(const name of ['gesturestart','gesturechange','gestureend'])document.removeEventListener(name,gesture);document.removeEventListener('wheel',wheel);document.removeEventListener('keydown',key);document.documentElement.classList.remove('pwa-fixed-scale');viewport?.setAttribute('content',original);};
}
