using System;
using System.IO;
using System.Drawing.Imaging;
using System.Web.Script.Serialization;
using System.Collections.Generic;
using Ohana3DS_Rebirth.Ohana;
using Ohana3DS_Rebirth.Ohana.Models;

class ExportModels {
    static void Main(string[] args) {
        var group=CGFX.load(args[0]);
        Directory.CreateDirectory(args[1]);
        var models=new List<object>();
        foreach(var model in group.model) {
            var meshes=new List<object>();
            foreach(var mesh in model.mesh) {
                var verts=new List<object>();
                foreach(var v in mesh.vertices) verts.Add(new {position=new[]{v.position.x,v.position.y,v.position.z},normal=new[]{v.normal.x,v.normal.y,v.normal.z},uv=new[]{v.texture0.x,v.texture0.y},color=v.diffuseColor,nodes=v.node,weights=v.weight});
                var mat=model.material[mesh.materialId];
                meshes.Add(new {name=mesh.name,visible=mesh.isVisible,texture=mat.name0,material=mat.name,coordinator=mat.textureCoordinator[0],mapper=mat.textureMapper[0],alphaTest=mat.fragmentShader.alphaTest,combiners=mat.fragmentShader.textureCombiner,colors=mat.materialColor,vertices=verts});
            }
            var record=new {name=model.name,meshes=meshes};
            var json=new JavaScriptSerializer(); json.MaxJsonLength=int.MaxValue;
            File.WriteAllText(Path.Combine(args[1],model.name+".json"),json.Serialize(record));
            Console.WriteLine(model.name+" meshes="+model.mesh.Count+" vertices="+model.verticesCount);
        }
        foreach(var tex in group.texture) {
            tex.texture.Save(Path.Combine(args[1],tex.name+".png"),ImageFormat.Png);
            Console.WriteLine("texture "+tex.name);
        }
    }
}



