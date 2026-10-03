const fs = require('fs');
const {mathjax} = require('mathjax-full/js/mathjax.js');
const {TeX} = require('mathjax-full/js/input/tex.js');
const {SVG} = require('mathjax-full/js/output/svg.js');
const {liteAdaptor} = require('mathjax-full/js/adaptors/liteAdaptor.js');
const {RegisterHTMLHandler} = require('mathjax-full/js/handlers/html.js');
require('mathjax-full/js/input/tex/AllPackages.js');
const {Resvg} = require('@resvg/resvg-js');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const adaptor=liteAdaptor();RegisterHTMLHandler(adaptor);
const tex=new TeX({packages:['base','ams','newcommand','boldsymbol','mathtools'],maxBuffer:20000,maxMacros:1000});
const doc=mathjax.document('',{InputJax:tex,OutputJax:new SVG({fontCache:'none'})});
try {
 const node=doc.convert(input.latex,{display:input.display!==false});
 let svg=adaptor.outerHTML(adaptor.firstChild(node));
 if(svg.includes('data-mjx-error')||svg.includes('data-mml-node="merror"'))throw Error('Formula LaTeX non supportata o non valida: '+adaptor.textContent(node));
 const box=svg.match(/viewBox="([^"]+)"/)[1].split(/\s+/).map(Number);
 const width=Math.max(4,Math.ceil(box[2]*48/1000));const height=Math.max(4,Math.ceil(box[3]*48/1000));
 if(width>12000||height>12000||width*height>25000000)throw Error('Formula troppo grande');
 svg=svg.replace(/width="[^"]+"/,`width="${width}"`).replace(/height="[^"]+"/,`height="${height}"`).replace(/currentColor/g,'#1d2939');
 const png=new Resvg(svg).render().asPng();
 process.stdout.write(JSON.stringify({png:png.toString('base64'),svg,width,height}));
} catch(error){process.stderr.write(error.message);process.exitCode=1;}
