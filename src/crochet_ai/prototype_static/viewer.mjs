export class SchematicViewer {
  constructor(canvas, onSelect) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.onSelect = onSelect;
    this.project = null;
    this.cursor = 0;
    this.mode = "full";
    this.yaw = -0.55;
    this.pitch = 0.2;
    this.zoom = 1;
    this.drag = null;
    this.projections = [];
    this.resizeObserver = new ResizeObserver(() => this.draw());
    this.resizeObserver.observe(canvas);
    canvas.addEventListener("pointerdown", event => this.pointerDown(event));
    canvas.addEventListener("pointermove", event => this.pointerMove(event));
    canvas.addEventListener("pointerup", event => this.pointerUp(event));
    canvas.addEventListener("pointercancel", () => { this.drag = null; });
    canvas.addEventListener("wheel", event => { event.preventDefault(); this.zoomBy(event.deltaY < 0 ? 1.08 : 1/1.08); }, { passive: false });
    canvas.addEventListener("keydown", event => {
      if (event.key === "ArrowLeft") { this.yaw -= .12; this.draw(); event.preventDefault(); }
      if (event.key === "ArrowRight") { this.yaw += .12; this.draw(); event.preventDefault(); }
      if (event.key === "ArrowUp") { this.pitch = Math.min(1.15, this.pitch + .08); this.draw(); event.preventDefault(); }
      if (event.key === "ArrowDown") { this.pitch = Math.max(-1.15, this.pitch - .08); this.draw(); event.preventDefault(); }
    });
  }
  setProject(project, cursor) { this.project = project; this.cursor = cursor; this.draw(); }
  setCursor(cursor) { this.cursor = cursor; this.draw(); }
  setMode(mode) { if (mode === "full" || mode === "progress") { this.mode = mode; this.draw(); } }
  zoomBy(factor) { this.zoom = Math.min(2.5, Math.max(.55, this.zoom * factor)); this.draw(); }
  reset() { this.yaw = -.55; this.pitch = .2; this.zoom = 1; this.draw(); }
  point(event) { const rect = this.canvas.getBoundingClientRect(); return { x: event.clientX - rect.left, y: event.clientY - rect.top }; }
  pointerDown(event) { this.drag = { ...this.point(event), moved: false }; this.canvas.setPointerCapture(event.pointerId); }
  pointerMove(event) { if (!this.drag) return; const p = this.point(event); const dx = p.x - this.drag.x, dy = p.y - this.drag.y; if (Math.abs(dx) + Math.abs(dy) > 2) this.drag.moved = true; this.yaw += dx * .009; this.pitch = Math.max(-1.15, Math.min(1.15, this.pitch + dy * .006)); this.drag.x = p.x; this.drag.y = p.y; this.draw(); }
  pointerUp(event) {
    if (!this.drag) return; const moved = this.drag.moved; this.drag = null; if (moved) return;
    const p = this.point(event); let nearest = null, distance = Infinity;
    for (const projected of this.projections) { const d = (projected.x-p.x)**2 + (projected.y-p.y)**2; if (d < distance) { nearest = projected; distance = d; } }
    if (nearest && distance < 24*24) this.onSelect?.(nearest.point.step_id);
  }
  draw() {
    const rect = this.canvas.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
    const width = Math.max(1, rect.width), height = Math.max(1, rect.height);
    this.canvas.width = Math.round(width * dpr); this.canvas.height = Math.round(height * dpr);
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const ctx = this.ctx; ctx.clearRect(0,0,width,height); ctx.fillStyle = "#ddd6c8"; ctx.fillRect(0,0,width,height);
    const projectPoints = this.project?.preview?.points || [];
    const steps = this.project?.steps || [];
    const stepIndex = new Map(steps.map((step,index)=>[step.step_id,index]));
    const stepsById = new Map(steps.map(step=>[step.step_id,step]));
    // A stitch point represents an actual stitch-produced top; ring anchors and other operation locations have no stitch_id.
    const points = projectPoints.filter(point => typeof point.stitch_id === "string" && stepsById.has(point.step_id));
    if (!points.length) {
      ctx.fillStyle = "#27332b"; ctx.textAlign = "center";
      ctx.font = "600 16px Segoe UI, sans-serif"; ctx.fillText("Noch keine Maschen im Aufbau", width/2, height/2 - 8);
      ctx.font = "14px Segoe UI, sans-serif"; ctx.fillText("Der Fadenring ist der Startanker, keine Maschenfläche.", width/2, height/2 + 20);
      this.projections=[]; return;
    }
    const xs=points.map(point=>point.xyz_mm[0]),ys=points.map(point=>point.xyz_mm[1]),zs=points.map(point=>point.xyz_mm[2]);
    const center=[(Math.min(...xs)+Math.max(...xs))/2,(Math.min(...ys)+Math.max(...ys))/2,(Math.min(...zs)+Math.max(...zs))/2];
    const ranges=[Math.max(...xs)-Math.min(...xs),Math.max(...ys)-Math.min(...ys),Math.max(...zs)-Math.min(...zs)];
    const radius=Math.max(1e-9,Math.hypot(...ranges)/2);
    const scale=Math.min(width,height)*.82/(2*radius)*this.zoom;
    const cy=Math.cos(this.yaw),sy=Math.sin(this.yaw),cp=Math.cos(this.pitch),sp=Math.sin(this.pitch);
    const allProjections=points.map(point=>{const x=point.xyz_mm[0]-center[0],y=point.xyz_mm[1]-center[1],z=point.xyz_mm[2]-center[2],rx=cy*x-sy*z,rz=sy*x+cy*z,ry=cp*y-sp*rz,depth=sp*y+cp*rz;return{point,x:width/2+rx*scale,y:height/2-ry*scale,depth};});
    const current=steps[this.cursor],currentId=current?.step_id;
    const visible=allProjections.filter(item=>this.mode==="full"||(stepIndex.get(item.point.step_id)<this.cursor)||(item.point.step_id===currentId));
    const visibleLocations=new Set(visible.map(item=>item.point.location_id));
    const projectionByLocation=new Map(allProjections.map(item=>[item.point.location_id,item]));
    const selectedTopIds=new Set(current?.top_location_ids||[]);
    const edge=(a,b,done,active)=>{ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.strokeStyle=active?"#75351f":done?"#9d4b2b":"#918a7c";ctx.lineWidth=active?2.8:done?2:1;ctx.stroke();};
    // Course rows follow the declared event and top-location order, including their cyclic closing edge.
    for(const course of (this.project?.courses||[])){
      const row=[];
      for(const step of steps){if(step.course_id!==course.course_id)continue;for(const id of (step.top_location_ids||[])){const point=projectionByLocation.get(id);if(point&&visibleLocations.has(id))row.push(point);}}
      const closeRow=this.mode==="full"||row.length===course.total_stitches;
      for(let index=0;index<row.length;index++){
        if(index===row.length-1&&!closeRow)break;
        const next=row[(index+1)%row.length]; if(row.length<2)break;
        const stepI=stepIndex.get(row[index].point.step_id),stepN=stepIndex.get(next.point.step_id);
        const active=row[index].point.step_id===currentId||next.point.step_id===currentId;
        edge(row[index],next,stepI<this.cursor&&stepN<this.cursor,active);
      }
    }
    // Cross-course connections use only declared base/top attachment identities.
    for(const step of steps){
      const topIds=step.top_location_ids||[],baseIds=step.base_location_ids||[];
      for(const topId of topIds){const top=projectionByLocation.get(topId);if(!top||!visibleLocations.has(topId))continue;for(const baseId of baseIds){const base=projectionByLocation.get(baseId);if(base&&visibleLocations.has(baseId))edge(base,top,stepIndex.get(step.step_id)<this.cursor,step.step_id===currentId);}}
    }
    visible.sort((a,b)=>a.depth-b.depth);this.projections=visible;
    for(const item of visible){const done=stepIndex.get(item.point.step_id)<this.cursor,active=item.point.step_id===currentId;ctx.beginPath();ctx.arc(item.x,item.y,active?6:done?4.5:3.4,0,Math.PI*2);ctx.fillStyle=active?"#75351f":done?"#9d4b2b":(item.point.color_hex||"#b88757");ctx.fill();ctx.strokeStyle="#27332b";ctx.lineWidth=active?1.4:.8;ctx.stroke();}
    if(this.mode==="progress"&&visible.length===0){ctx.fillStyle="#27332b";ctx.textAlign="center";ctx.font="600 15px Segoe UI, sans-serif";ctx.fillText("Noch keine Maschen im Aufbau",width/2,height/2);}
  }
}
