using System.Runtime.InteropServices;
using Microsoft.ML.OnnxRuntime;
using Microsoft.ML.OnnxRuntime.Tensors;
using OpenCvSharp;
using OpenCvSharp.Dnn;

namespace desktop;

public record Detection(Rect Box, float Score);

// Same pre/post-processing as detect() in scripts/predict_onnx.py.
public sealed class Detector : IDisposable
{
    const int Size = 640;  // model input is fixed at 1x3x640x640, see README "ONNX model format"
    readonly InferenceSession session;
    readonly string inputName;

    public Detector(string modelPath)
    {
        session = new InferenceSession(modelPath);
        inputName = session.InputMetadata.Keys.First();
    }

    /// <summary>Boxes in pixels of the original BGR image.</summary>
    public List<Detection> Detect(Mat image, float conf = 0.25f, float iou = 0.45f)
    {
        // Letterbox: keep aspect ratio, pad with grey 114.
        float scale = Math.Min((float)Size / image.Height, (float)Size / image.Width);
        int newW = (int)Math.Round(image.Width * scale), newH = (int)Math.Round(image.Height * scale);
        int padX = (Size - newW) / 2, padY = (Size - newH) / 2;
        using var padded = new Mat(Size, Size, MatType.CV_8UC3, new Scalar(114, 114, 114));
        using (var resized = image.Resize(new OpenCvSharp.Size(newW, newH)))
        using (var roi = padded[new Rect(padX, padY, newW, newH)])
            resized.CopyTo(roi);

        // BGR -> RGB, 0-1, NCHW
        using var blob = CvDnn.BlobFromImage(padded, 1 / 255.0, swapRB: true);
        var data = new float[3 * Size * Size];
        Marshal.Copy(blob.Data, data, 0, data.Length);
        var input = new DenseTensor<float>(data, [1, 3, Size, Size]);

        using var results = session.Run([NamedOnnxValue.CreateFromTensor(inputName, input)]);
        var output = results[0].AsTensor<float>();  // (1, 4 + classes, 8400): cx, cy, w, h, scores
        int channels = output.Dimensions[1], count = output.Dimensions[2];

        var boxes = new List<Rect>();
        var scores = new List<float>();
        for (int i = 0; i < count; i++)
        {
            float score = 0;
            for (int c = 4; c < channels; c++) score = Math.Max(score, output[0, c, i]);
            if (score < conf) continue;
            float w = output[0, 2, i], h = output[0, 3, i];
            float x = (output[0, 0, i] - w / 2 - padX) / scale;
            float y = (output[0, 1, i] - h / 2 - padY) / scale;
            boxes.Add(new Rect((int)x, (int)y, (int)(w / scale), (int)(h / scale)));
            scores.Add(score);
        }

        CvDnn.NMSBoxes(boxes, scores, conf, iou, out int[] keep);
        return keep.Select(i => new Detection(boxes[i], scores[i])).ToList();
    }

    public void Dispose() => session.Dispose();
}
