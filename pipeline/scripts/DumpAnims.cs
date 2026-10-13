using System;
using System.IO;
using System.Collections.Generic;
using System.Web.Script.Serialization;
using Ohana3DS_Rebirth.Ohana;
using Ohana3DS_Rebirth.Ohana.Models;

// Dumps skeletons (bind pose) and skeletal animations of a .bcres to JSON.
// Usage: DumpAnims.exe file.bcres out.json [sampleAll]
class DumpAnims {
    static object Group(RenderBase.OAnimationKeyFrameGroup g) {
        if (g == null || !g.exists) return null;
        var k = new List<float[]>();
        foreach (var f in g.keyFrames) k.Add(new[] { f.frame, f.value, f.inSlope, f.outSlope });
        return new { interp = g.interpolation.ToString(), keys = k };
    }
    static object Frame(RenderBase.OAnimationFrame f) {
        if (f == null || !f.exists) return null;
        var v = new List<float[]>();
        foreach (var q in f.vector) v.Add(new[] { q.x, q.y, q.z, q.w });
        return new { start = f.startFrame, end = f.endFrame, v = v };
    }
    static void Main(string[] args) {
        var group = CGFX.load(args[0]);
        var models = new List<object>();
        foreach (var model in group.model) {
            var bones = new List<object>();
            foreach (var b in model.skeleton)
                bones.Add(new { name = b.name, parent = b.parentId, t = new[] { b.translation.x, b.translation.y, b.translation.z }, r = new[] { b.rotation.x, b.rotation.y, b.rotation.z }, s = new[] { b.scale.x, b.scale.y, b.scale.z } });
            models.Add(new { name = model.name, bones = bones });
        }
        var anims = new List<object>();
        foreach (RenderBase.OSkeletalAnimation a in group.skeletalAnimation.list) {
            var bl = new List<object>();
            foreach (var b in a.bone) {
                bl.Add(new {
                    name = b.name, frameFormat = b.isFrameFormat, axisAngle = b.isAxisAngle, baked = b.isFullBakedFormat,
                    rx = Group(b.rotationX), ry = Group(b.rotationY), rz = Group(b.rotationZ),
                    tx = Group(b.translationX), ty = Group(b.translationY), tz = Group(b.translationZ),
                    sx = Group(b.scaleX), sy = Group(b.scaleY), sz = Group(b.scaleZ),
                    rq = Frame(b.rotationQuaternion), tq = Frame(b.translation), sq = Frame(b.scale)
                });
            }
            anims.Add(new { name = a.name, frames = a.frameSize, loop = a.loopMode.ToString(), bones = bl });
        }
        var json = new JavaScriptSerializer(); json.MaxJsonLength = int.MaxValue;
        File.WriteAllText(args[1], json.Serialize(new { models = models, anims = anims }));
        Console.WriteLine("models=" + models.Count + " anims=" + anims.Count);
    }
}
