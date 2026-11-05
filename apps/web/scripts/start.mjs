import {cpSync,existsSync} from "node:fs";
import {spawn} from "node:child_process";
if(!existsSync(".next/standalone/server.js")){console.error("Run npm run build before npm start.");process.exit(1);}
cpSync(".next/static",".next/standalone/.next/static",{recursive:true});
if(existsSync("public"))cpSync("public",".next/standalone/public",{recursive:true});
const server=spawn(process.execPath,[".next/standalone/server.js"],{stdio:"inherit",env:{...process.env,PORT:process.env.PORT??"3101",HOSTNAME:"0.0.0.0"}});
for(const signal of ["SIGINT","SIGTERM"])process.on(signal,()=>server.kill(signal));
server.on("exit",code=>process.exit(code??0));
