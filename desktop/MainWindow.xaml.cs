using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.IO.Ports;
using System.Windows;
using System.Windows.Media;
using Microsoft.Win32;
using OpenCvSharp;
using OpenCvSharp.WpfExtensions;

namespace desktop;

public partial class MainWindow : System.Windows.Window
{
    static readonly TimeSpan CameraAlertGap = TimeSpan.FromSeconds(5);  // don't flood the Arduino; the sketch enforces the 10 min SMS cooldown
    static readonly Scalar BoxColor = new(56, 68, 240);  // BGR of #F04438
    static readonly string[] ImageExtensions = [".jpg", ".jpeg", ".png", ".bmp"];

    readonly Detector detector;
    SerialPort? port;
    string serialBuffer = "";
    bool moduleMissing;  // sketch reported NO MODULE since the last connect
    CancellationTokenSource? cameraStop;
    Task? cameraTask;
    DateTime lastAlert = DateTime.MinValue;
    readonly Stopwatch frameClock = new();
    double fps;

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
        int index = CameraIndex.SelectedIndex;
        SetCameraButton(running: true);
        CameraIndex.IsEnabled = false;
        SetSource($"Camera {index} · starting…", live: true);
        fps = 0;
        frameClock.Restart();
        var token = cameraStop.Token;
        cameraTask = Task.Run(() => RunCamera(index, token));
        try { await cameraTask; }
        catch (Exception ex) { Write(ex.Message); SetSource($"Camera {index} unavailable", live: false); }
        finally
        {
            cameraStop = null;
            SetCameraButton(running: false);
            CameraIndex.IsEnabled = true;
            if (LiveDot.Visibility == Visibility.Visible) SetSource($"Camera {index} · stopped", live: false);
            StatusRight.Text = "Idle";
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

    void SetCameraButton(bool running)
    {
        CameraButton.Style = (Style)FindResource(running ? "SecondaryButton" : "PrimaryButton");
        CameraButtonIcon.Text = running ? "" : "";  // Stop / Play
        CameraButtonText.Text = running ? "Stop camera" : "Start camera";
    }

    // ---- image import ----

    void OpenImage_Click(object sender, RoutedEventArgs e)
    {
        var dialog = new OpenFileDialog { Filter = "Images|*.jpg;*.jpeg;*.png;*.bmp|All files|*.*" };
        if (dialog.ShowDialog() == true) OpenImage(dialog.FileName);
    }

    void Stage_Drop(object sender, DragEventArgs e)
    {
        if (e.Data.GetData(DataFormats.FileDrop) is not string[] files) return;
        var file = files.FirstOrDefault(f => ImageExtensions.Contains(Path.GetExtension(f).ToLowerInvariant()));
        if (file == null) { Write("Drop a .jpg, .png or .bmp image."); return; }
        OpenImage(file);
    }

    async void OpenImage(string path)
    {
        if (cameraStop != null)
        {
            cameraStop.Cancel();
            try { await cameraTask!; } catch { }  // already reported by Camera_Click
        }

        using var image = Cv2.ImRead(path);
        if (image.Empty()) { Write($"Cannot read {path}"); return; }
        var detections = await Task.Run(() => detector.Detect(image));
        Write($"{Path.GetFileName(path)}: {detections.Count(d => d.Score >= MinScore.Value)} detection(s)");
        SetSource(Path.GetFileName(path), live: false);
        StatusRight.Text = $"{image.Width} × {image.Height}";
        Show(image, detections, fromCamera: false);
    }

    // ---- shared: draw, display, alert ----

    void Show(Mat image, List<Detection> detections, bool fromCamera)
    {
        var found = detections.Where(d => d.Score >= MinScore.Value).ToList();
        int thickness = Math.Max(2, image.Width / 400);
        double fontScale = Math.Max(0.5, image.Width / 1400.0);
        foreach (var d in found)
        {
            Cv2.Rectangle(image, d.Box, BoxColor, thickness, LineTypes.AntiAlias);
            string label = $"BCC {d.Score:0.00}";
            var size = Cv2.GetTextSize(label, HersheyFonts.HersheySimplex, fontScale, 1, out int baseline);
            int top = Math.Max(d.Box.Y - size.Height - baseline - 6, 0);
            Cv2.Rectangle(image, new OpenCvSharp.Rect(d.Box.X, top, size.Width + 10, size.Height + baseline + 6), BoxColor, -1);
            Cv2.PutText(image, label, new OpenCvSharp.Point(d.Box.X + 5, top + size.Height + 3),
                HersheyFonts.HersheySimplex, fontScale, Scalar.White, 1, LineTypes.AntiAlias);
        }
        View.Source = image.ToBitmapSource();
        EmptyState.Visibility = Visibility.Collapsed;
        SetResult(found);

        if (fromCamera)
        {
            double dt = frameClock.Elapsed.TotalSeconds;
            frameClock.Restart();
            if (dt > 0) fps = fps == 0 ? 1 / dt : fps * 0.9 + 0.1 / dt;
            SourceText.Text = $"Camera {CameraIndex.SelectedIndex} · live";
            StatusRight.Text = $"{image.Width} × {image.Height} · {fps:0} fps";
        }

        if (found.Count == 0) return;
        if (fromCamera && DateTime.Now - lastAlert < CameraAlertGap) return;
        lastAlert = DateTime.Now;
        SendAlert(found.Max(d => d.Score));
    }

    void SetResult(List<Detection> found)
    {
        if (found.Count == 0)
        {
            SetResultCard("ClearBg", "ClearFg", "", "No BCC detected",
                $"Nothing above {MinScore.Value:0.00} confidence.");
            return;
        }
        string regions = found.Count == 1 ? "1 region" : $"{found.Count} regions";
        SetResultCard("AlertBg", "AlertFg", "", "Possible BCC detected",
            $"{regions} · top confidence {found.Max(d => d.Score):0.00}");
    }

    void SetResultCard(string bg, string fg, string icon, string title, string detail)
    {
        var fgBrush = (Brush)FindResource(fg);
        ResultCard.Background = (Brush)FindResource(bg);
        ResultIcon.Text = icon;
        ResultIcon.Foreground = fgBrush;
        ResultTitle.Text = title;
        ResultTitle.Foreground = fgBrush;
        ResultDetail.Text = detail;
    }

    void SetSource(string text, bool live)
    {
        SourceBadge.Visibility = Visibility.Visible;
        LiveDot.Visibility = live ? Visibility.Visible : Visibility.Collapsed;
        SourceText.Text = text;
    }

    void SendAlert(float score)
    {
        string line = "ALERT " + score.ToString("0.00", CultureInfo.InvariantCulture);
        if (port is not { IsOpen: true })
        {
            Write($"{line} (no Arduino connected, no SMS sent)");
            SetLastAlert($"Detection at {DateTime.Now:HH:mm:ss}, not sent (no Arduino).");
            return;
        }
        try
        {
            port.WriteLine(line);
            Write($"{line} sent to Arduino");
            SetLastAlert($"Alert sent to Arduino at {DateTime.Now:HH:mm:ss}.");
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
            PortBox.IsEnabled = true;
            SetArduino("InkFaint", "Arduino not connected");
            Write("Arduino disconnected.");
            return;
        }
        if (PortBox.SelectedItem is not string name) { Write("Pick the Arduino's COM port first."); return; }

        try
        {
            port = new SerialPort(name, 9600) { NewLine = "\n" };
            serialBuffer = "";
            moduleMissing = false;
            port.DataReceived += (s, _) =>
            {
                string text = ((SerialPort)s).ReadExisting();
                Dispatcher.BeginInvoke(() => OnSerial(text));
            };
            port.Open();  // this resets an Uno/Nano; wait for "READY" before expecting an SMS
            ConnectButton.Content = "Disconnect";
            PortBox.IsEnabled = false;
            SetArduino("WarnFg", "Waiting for Arduino…");
            Write($"Connected to {name}, waiting for READY...");
        }
        catch (Exception ex)
        {
            port = null;
            SetArduino("AlertFg", $"Cannot open {name}");
            Write($"Cannot open {name}: {ex.Message} (is the Arduino IDE Serial Monitor open?)");
        }
    }

    // Reads arrive in arbitrary chunks; only act on whole lines.
    void OnSerial(string text)
    {
        serialBuffer += text;
        int newline;
        while ((newline = serialBuffer.IndexOf('\n')) >= 0)
        {
            string line = serialBuffer[..newline].Trim();
            serialBuffer = serialBuffer[(newline + 1)..];
            if (line.Length == 0) continue;
            Write("Arduino: " + line);
            // replies from firmware/asclepius_sms
            if (line == "READY")
            {
                if (!moduleMissing) SetArduino("ClearFg", "Ready to send SMS");
            }
            else if (line.StartsWith("NO MODULE"))
            {
                moduleMissing = true;
                SetArduino("AlertFg", "Arduino OK, SIM800C not answering");
            }
            else if (line == "SENT")
            {
                moduleMissing = false;
                SetArduino("ClearFg", "Ready to send SMS");
                SetLastAlert($"SMS sent at {DateTime.Now:HH:mm:ss}.");
            }
            else if (line.StartsWith("FAILED"))
                SetLastAlert($"SMS failed at {DateTime.Now:HH:mm:ss}: {line[6..].Trim()}", failed: true);
            else if (line == "COOLDOWN")
                SetLastAlert($"SMS skipped at {DateTime.Now:HH:mm:ss} (10 min cooldown).");
        }
    }

    void SetLastAlert(string text, bool failed = false)
    {
        LastAlert.Text = text;
        if (failed) LastAlert.SetResourceReference(System.Windows.Controls.TextBlock.ForegroundProperty, "AlertFg");
        else LastAlert.ClearValue(System.Windows.Controls.TextBlock.ForegroundProperty);  // back to the Hint style
    }

    void SetArduino(string brush, string text)
    {
        ArduinoDot.Fill = (Brush)FindResource(brush);
        ArduinoStatus.Text = text;
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
