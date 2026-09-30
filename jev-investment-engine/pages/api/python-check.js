let runtimePromise;
async function getRuntime(){
  if(!runtimePromise){
    runtimePromise=(async()=>{
      const { loadPyodide } = await import("pyodide");
      return await loadPyodide();
    })();
  }
  return runtimePromise;
}
export const config={maxDuration:60};
export default async function handler(req,res){
  res.setHeader("Cache-Control","no-store");
  if(process.env.VERCEL_ENV!=="preview") return res.status(404).json({ok:false,error:"preview_only"});
  try{
    const py=await getRuntime();
    const value=py.runPython("import sys\n(sys.version, sum(i*i for i in range(10)))");
    const arr=value.toJs ? value.toJs() : value;
    if(value?.destroy) value.destroy();
    return res.status(200).json({ok:true,python_version:String(arr[0]),sum_squares:Number(arr[1]),engine:"pyodide"});
  }catch(e){
    return res.status(500).json({ok:false,error:String(e?.message||e),stack:String(e?.stack||"").slice(0,1000)});
  }
}
