import { execFile } from "child_process";
import { promisify } from "util";
const execFileP=promisify(execFile);
export default async function handler(req,res){
  res.setHeader("Cache-Control","no-store");
  if(process.env.VERCEL_ENV!=="preview") return res.status(404).json({ok:false,error:"preview_only"});
  try{
    const {stdout,stderr}=await execFileP("python3",["-c","import sys; print(sys.version); print('PYTHON_OK')"],{timeout:10000,maxBuffer:1024*1024});
    return res.status(200).json({ok:true,stdout,stderr});
  }catch(e){return res.status(500).json({ok:false,error:e.code||e.message||"python_failed"});}
}
