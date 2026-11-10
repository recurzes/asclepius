using System.Globalization;
using System.IO;
using System.IO.Ports;
using System.Windows;
using Microsoft.Win32;
using OpenCvSharp;
using OpenCvSharp.WpfExtensions;

namespace desktop;

public partial class MainWindow : System.Windows.Window
{
    static readonly TimeSpan CameraAlertGap = TimeSpan.FromSeconds(5);  // don't flood the Arduino; the sketch enforces the 10 min SMS cooldown

    readonly Detector detector;
    SerialPort? port;
    CancellationTokenSource? cameraStop;
    Task? cameraTask;
    DateTime lastAlert = DateTime.MinValue;

    public MainWindow()
    {
        InitializeComponent();
        detector = new Detector(Path.Combine(AppContext.BaseDirectory, "asclepius_bcc.onnx"));
        PortBox_DropDownOpened(null, EventArgs.Empty);
        Write("Ready. Connect the Arduino, then start the camera or open an image.");
    }

    // ---- camera ----

    async void Camera_Click(object sender, RoutedEventArgs e)
    {
        if (cameraStop != null) { cameraStop.Cancel(); return; }

        cameraStop = new CancellationTokenSource();
        CameraButton.Content = "Stop camera";
        int index = (int)CameraIndex.SelectedItem;
        var token = cameraStop.Token;
        cameraTask = Task.Run(() => RunCamera(index, token));
        try { await cameraTask; }
        catch (Exception ex) { Write(ex.Message); }
        finally
        {
            cameraStop = null;
            CameraButton.Content = "Start camera";
        }
    }

    void RunCamera(int index, CancellationToken token)
    {
        using var camera = new VideoCapture(index);
        if (!camera.IsOpened()) throw new InvalidOperationException($"Cannot open camera {index}.");
        using var frame = new Mat();
        while (!token.IsCancellationRequested && camera.Read(frame) && !frame.Empty())
        {
            var detections = detector.Detect(frame);
            Dispatcher.Invoke(() => Show(frame, detections, fromCamera: true));
        }
    }

    // ---- image import ----

    async void OpenImage_Click(object sender, RoutedEventArgs e)
    {
        var dialog = new OpenFileDialog { Filter = "Images|*.jpg;*.jpeg;*.png;*.bmp|All files|*.*" };
        if (dialog.ShowDialog() != true) return;

        if (cameraStop != null)
        {
            cameraStop.Cancel();
            try { await cameraTask!; } catch { }  // already reported by Camera_Click
        }

        using var image = Cv2.ImRead(dialog.FileName);
        if (image.Empty()) { Write($"Cannot read {dialog.FileName}"); return; }
        var detections = await Task.Run(() => detector.Detect(image));
        Write($"{Path.GetFileName(dialog.FileName)}: {detections.Count(d => d.Score >= MinScore.Value)} detection(s)");
        Show(image, detections, fromCamera: false);
    }

    // ---- shared: draw, display, alert ----

    void Show(Mat image, List<Detection> detections, bool fromCamera)
    {
        var found = detections.Where(d => d.Score >= MinScore.Value).ToList();
        foreach (var d in found)
        {
            Cv2.Rectangle(image, d.Box, Scalar.Red, 2);
            Cv2.PutText(image, $"BCC {d.Score:0.00}", new OpenCvSharp.Point(d.Box.X, Math.Max(d.Box.Y - 8, 16)),
                HersheyFonts.HersheySimplex, 0.6, Scalar.Red, 2);
        }
        View.Source = image.ToBitmapSource();

        if (found.Count == 0) return;
        if (fromCamera && DateTime.Now - lastAlert < CameraAlertGap) return;
        lastAlert = DateTime.Now;
        SendAlert(found.Max(d => d.Score));
    }

    void SendAlert(float score)
    {
        string line = "ALERT " + score.ToString("0.00", CultureInfo.InvariantCulture);
        if (port is not { IsOpen: true }) { Write($"{line} (no Arduino connected, no SMS sent)"); return; }
        try
        {
            port.WriteLine(line);
            Write($"{line} sent to Arduino");
        }
        catch (Exception ex) { Write($"Arduino write failed: {ex.Message}"); }
    }

    // ---- Arduino ----

    void PortBox_DropDownOpened(object? sender, EventArgs e)
    {
        var selected = PortBox.SelectedItem;
        PortBox.ItemsSource = SerialPort.GetPortNames();
        PortBox.SelectedItem = selected ?? PortBox.Items.Cast<object>().LastOrDefault();
    }

    void Connect_Click(object sender, RoutedEventArgs e)
    {
        if (port is { IsOpen: true })
        {
            port.Close();
            port = null;
            ConnectButton.Content = "Connect";
            Write("Arduino disconnected.");
            return;
        }
        if (PortBox.SelectedItem is not string name) { Write("Pick the Arduino's COM port first."); return; }

        try
        {
            port = new SerialPort(name, 9600) { NewLine = "\n" };
            port.DataReceived += (s, _) =>
            {
                string text = ((SerialPort)s).ReadExisting();
                Dispatcher.BeginInvoke(() => Write("Arduino: " + text.Trim()));
            };
            port.Open();  // this resets an Uno/Nano; wait for "READY" before expecting an SMS
            ConnectButton.Content = "Disconnect";
            Write($"Connected to {name}, waiting for READY...");
        }
        catch (Exception ex)
        {
            port = null;
            Write($"Cannot open {name}: {ex.Message} (is the Arduino IDE Serial Monitor open?)");
        }
    }

    // ---- misc ----

    void Write(string message)
    {
        Log.AppendText($"{DateTime.Now:HH:mm:ss}  {message}\n");
        Log.ScrollToEnd();
    }

    void Window_Closing(object? sender, System.ComponentModel.CancelEventArgs e)
    {
        cameraStop?.Cancel();
        port?.Close();
    }
}
