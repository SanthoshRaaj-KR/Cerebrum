// Cerebrum's desktop launcher.
//
// One double-click on the desktop has to bring up two services, say
// honestly how far along it is, and - the part people forget - put them
// both down again cleanly afterwards. A stale node process holding port
// 3000 is the difference between "click it again" and "why is it broken".
//
// It does NOT reimplement start.ps1. That script already knows how to
// build the virtualenv, install both dependency sets, check the keys and
// tree-kill what it spawned; a second copy of that logic would drift, and
// the copy you were not using would be the broken one. This is a window
// around it: it runs the script, reads its output, watches the two ports
// itself, and owns the browser tab (hence -NoBrowser).
//
// C# 5 only - this is built by the .NET Framework csc.exe that ships with
// Windows, so the whole thing compiles on a clean machine with no SDK to
// install. No string interpolation, no null-conditionals.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Text;
using System.IO;
using System.Net.Sockets;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Windows.Forms;

namespace Cerebrum
{
    /// The console's dark palette, lifted from web/app/tokens.css so the
    /// launcher and the thing it launches are visibly the same product.
    static class Palette
    {
        public static readonly Color Bg = FromHex("#020617");       // slate-950
        public static readonly Color Surface = FromHex("#0f172a");  // slate-900
        public static readonly Color Sunken = FromHex("#0b1120");
        public static readonly Color Border = FromHex("#1e293b");   // slate-800
        public static readonly Color Text = FromHex("#f1f5f9");     // slate-100
        public static readonly Color Muted = FromHex("#94a3b8");    // slate-400
        public static readonly Color Subtle = FromHex("#64748b");   // slate-500
        public static readonly Color Accent = FromHex("#38bdf8");   // blue-400
        public static readonly Color AccentLift = FromHex("#7dd3fc");
        public static readonly Color AccentDim = FromHex("#0369a1");
        public static readonly Color Ok = FromHex("#4ade80");       // green-400
        public static readonly Color Warn = FromHex("#fbbf24");     // amber-400
        public static readonly Color Bad = FromHex("#f87171");      // red-400

        public static Color FromHex(string hex)
        {
            return ColorTranslator.FromHtml(hex);
        }
    }

    /// Picks the first typeface actually installed. IBM Plex is what the
    /// console uses; nothing guarantees it is on this machine, and a
    /// silently-substituted fallback is how a careful layout turns into a
    /// ransom note.
    static class Fonts
    {
        static readonly HashSet<string> Installed = LoadInstalled();

        static HashSet<string> LoadInstalled()
        {
            HashSet<string> names = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            try
            {
                foreach (FontFamily f in FontFamily.Families) names.Add(f.Name);
            }
            catch { }
            return names;
        }

        static string First(string[] wanted, string fallback)
        {
            foreach (string name in wanted) if (Installed.Contains(name)) return name;
            return fallback;
        }

        static readonly string SansName = First(
            new string[] { "IBM Plex Sans", "Segoe UI Variable Text", "Segoe UI" }, "Arial");
        static readonly string MonoName = First(
            new string[] { "IBM Plex Mono", "Cascadia Mono", "Consolas" }, "Courier New");

        public static Font Sans(float size, FontStyle style) { return new Font(SansName, size, style); }
        public static Font Mono(float size, FontStyle style) { return new Font(MonoName, size, style); }
    }

    static class Draw
    {
        public static GraphicsPath Rounded(Rectangle r, int radius)
        {
            int d = radius * 2;
            GraphicsPath p = new GraphicsPath();
            p.AddArc(r.X, r.Y, d, d, 180, 90);
            p.AddArc(r.Right - d, r.Y, d, d, 270, 90);
            p.AddArc(r.Right - d, r.Bottom - d, d, d, 0, 90);
            p.AddArc(r.X, r.Bottom - d, d, d, 90, 90);
            p.CloseFigure();
            return p;
        }

        public static void Fill(Graphics g, Rectangle r, int radius, Color c)
        {
            using (GraphicsPath p = Rounded(r, radius))
            using (SolidBrush b = new SolidBrush(c))
                g.FillPath(b, p);
        }

        public static void Outline(Graphics g, Rectangle r, int radius, Color c)
        {
            using (GraphicsPath p = Rounded(r, radius))
            using (Pen pen = new Pen(c))
                g.DrawPath(pen, p);
        }

        /// The Cerebrum mark: the wordmark's C in a rounded accent tile.
        /// Same two hex values and same gradient as the desktop icon that
        /// tools/launcher/build.ps1 draws, so the thing you clicked and the
        /// window that opens are recognisably one object.
        public static void Mark(Graphics g, Rectangle r)
        {
            using (GraphicsPath p = Rounded(r, r.Width / 4))
            using (LinearGradientBrush b =
                       new LinearGradientBrush(r, Palette.Accent, Palette.AccentDim, 55f))
                g.FillPath(b, p);
            using (Font f = Fonts.Sans(r.Height * 0.52f, FontStyle.Bold))
            using (StringFormat sf = new StringFormat())
            {
                sf.Alignment = StringAlignment.Center;
                sf.LineAlignment = StringAlignment.Center;
                g.DrawString("C", f, Brushes.White, r, sf);
            }
        }
    }

    /// Blocked is not Failed: nothing went wrong, something is simply in
    /// the way. Drawing it in the same red as a real failure would make
    /// the mark disagree with the word on the status pill next to it.
    enum StepState { Pending, Active, Done, Blocked, Failed }

    /// The progress stepper.
    ///
    /// Painted rather than assembled out of a dozen labels: the rail
    /// between the dots is the whole point - it says these are one
    /// sequence with a position in it, not four unrelated lines - and that
    /// is a drawing, not a layout.
    class Stepper : Control
    {
        const int RowHeight = 52;
        const int DotX = 22;
        const int DotR = 9;

        readonly string[] labels;
        readonly StepState[] states;
        string detail = "";
        int spin;
        readonly System.Windows.Forms.Timer ticker;   // qualified: System.Threading has one too

        public Stepper(string[] stepLabels)
        {
            labels = stepLabels;
            states = new StepState[labels.Length];
            SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.UserPaint |
                     ControlStyles.OptimizedDoubleBuffer | ControlStyles.ResizeRedraw, true);
            BackColor = Palette.Bg;
            Height = RowHeight * labels.Length + 8;

            // Runs only while a step is actually active, so the window is
            // not repainting itself thirty times a second for no reason
            // once everything is up.
            ticker = new System.Windows.Forms.Timer();
            ticker.Interval = 33;
            ticker.Tick += delegate { spin = (spin + 14) % 360; Invalidate(); };
        }

        public void Set(int index, StepState state)
        {
            if (index < 0 || index >= states.Length) return;
            states[index] = state;
            // Everything before a started step is finished by definition.
            if (state != StepState.Pending)
                for (int i = 0; i < index; i++)
                    if (states[i] != StepState.Failed) states[i] = StepState.Done;
            UpdateTicker();
            Invalidate();
        }

        public void SetDetail(string text)
        {
            detail = text == null ? "" : text;
            Invalidate();
        }

        public void FailActive(string why)
        {
            bool marked = false;
            for (int i = 0; i < states.Length; i++)
                if (states[i] == StepState.Active) { states[i] = StepState.Failed; marked = true; }
            if (!marked) states[0] = StepState.Failed;
            SetDetail(why);
            UpdateTicker();
            Invalidate();
        }

        public void Reset()
        {
            for (int i = 0; i < states.Length; i++) states[i] = StepState.Pending;
            detail = "";
            UpdateTicker();
            Invalidate();
        }

        void UpdateTicker()
        {
            bool anyActive = false;
            foreach (StepState s in states) if (s == StepState.Active) anyActive = true;
            ticker.Enabled = anyActive;
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            Graphics g = e.Graphics;
            g.SmoothingMode = SmoothingMode.AntiAlias;
            g.TextRenderingHint = TextRenderingHint.ClearTypeGridFit;

            using (Font label = Fonts.Sans(10f, FontStyle.Regular))
            using (Font labelOn = Fonts.Sans(10f, FontStyle.Bold))
            using (Font small = Fonts.Mono(8.25f, FontStyle.Regular))
            {
                for (int i = 0; i < labels.Length; i++)
                {
                    int cy = 18 + i * RowHeight;
                    StepState st = states[i];

                    // The rail. Accent behind a finished step, so the line
                    // itself reads as how far you have got.
                    if (i < labels.Length - 1)
                    {
                        Color rail = st == StepState.Done ? Palette.AccentDim : Palette.Border;
                        using (Pen p = new Pen(rail, 2f))
                            g.DrawLine(p, DotX, cy + DotR + 3, DotX, cy + RowHeight - DotR - 3);
                    }

                    Rectangle dot = new Rectangle(DotX - DotR, cy - DotR, DotR * 2, DotR * 2);
                    if (st == StepState.Done)
                    {
                        using (SolidBrush b = new SolidBrush(Palette.Accent)) g.FillEllipse(b, dot);
                        using (Pen p = new Pen(Palette.Bg, 2f))
                        {
                            p.StartCap = LineCap.Round;
                            p.EndCap = LineCap.Round;
                            g.DrawLines(p, new Point[] {
                                new Point(dot.X + 5, cy),
                                new Point(dot.X + 8, cy + 3),
                                new Point(dot.Right - 4, cy - 4) });
                        }
                    }
                    else if (st == StepState.Blocked)
                    {
                        using (SolidBrush b = new SolidBrush(Palette.Warn)) g.FillEllipse(b, dot);
                        using (Pen p = new Pen(Palette.Bg, 2f))
                        {
                            p.StartCap = LineCap.Round;
                            p.EndCap = LineCap.Round;
                            g.DrawLine(p, DotX, cy - 4, DotX, cy + 1);
                        }
                        // The dot of the exclamation mark. A zero-length
                        // DrawLine renders nothing, so it has to be a shape.
                        using (SolidBrush b = new SolidBrush(Palette.Bg))
                            g.FillEllipse(b, DotX - 1, cy + 3, 2.5f, 2.5f);
                    }
                    else if (st == StepState.Failed)
                    {
                        using (SolidBrush b = new SolidBrush(Palette.Bad)) g.FillEllipse(b, dot);
                        using (Pen p = new Pen(Palette.Bg, 2f))
                        {
                            p.StartCap = LineCap.Round;
                            p.EndCap = LineCap.Round;
                            g.DrawLine(p, dot.X + 6, cy - 3, dot.Right - 6, cy + 3);
                            g.DrawLine(p, dot.X + 6, cy + 3, dot.Right - 6, cy - 3);
                        }
                    }
                    else if (st == StepState.Active)
                    {
                        using (Pen track = new Pen(Palette.Border, 2.5f)) g.DrawEllipse(track, dot);
                        using (Pen arc = new Pen(Palette.Accent, 2.5f))
                        {
                            arc.StartCap = LineCap.Round;
                            arc.EndCap = LineCap.Round;
                            g.DrawArc(arc, dot, spin, 100);
                        }
                    }
                    else
                    {
                        using (Pen p = new Pen(Palette.Border, 2.5f)) g.DrawEllipse(p, dot);
                    }

                    Color fg = st == StepState.Pending ? Palette.Subtle
                             : st == StepState.Failed ? Palette.Bad
                             : st == StepState.Blocked ? Palette.Warn
                             : st == StepState.Active ? Palette.Text : Palette.Muted;
                    Font font = st == StepState.Active || st == StepState.Blocked ? labelOn : label;
                    bool hasDetail = st != StepState.Pending && st != StepState.Done
                                     && detail.Length > 0;
                    TextRenderer.DrawText(g, labels[i], font,
                        new Point(DotX + 22, hasDetail ? cy - 15 : cy - 9), fg,
                        TextFormatFlags.NoPadding);

                    // The running commentary sits under whichever step it
                    // belongs to, so there is never a status line floating
                    // free of the thing it describes.
                    if (hasDetail)
                    {
                        Rectangle box = new Rectangle(DotX + 22, cy + 3, Width - DotX - 34, 18);
                        TextRenderer.DrawText(g, detail, small, box,
                            st == StepState.Failed ? Palette.Bad
                                : st == StepState.Blocked ? Palette.Warn : Palette.Subtle,
                            TextFormatFlags.NoPadding | TextFormatFlags.EndEllipsis |
                            TextFormatFlags.SingleLine);
                    }
                }
            }
        }
    }

    /// A button that belongs to this palette rather than to Windows 98.
    class FlatButton : Button
    {
        readonly bool primary;

        public FlatButton(string text, bool isPrimary)
        {
            primary = isPrimary;
            Text = text;
            AutoSize = false;
            Size = new Size(150, 38);      // comfortably past the 24px target minimum
            FlatStyle = FlatStyle.Flat;
            FlatAppearance.BorderSize = 1;
            Font = Fonts.Sans(9.25f, primary ? FontStyle.Bold : FontStyle.Regular);
            UseVisualStyleBackColor = false;
            Restyle();
            EnabledChanged += delegate { Restyle(); };
        }

        void Restyle()
        {
            if (!Enabled)
            {
                BackColor = Palette.Surface;
                ForeColor = Palette.Subtle;
                FlatAppearance.BorderColor = Palette.Border;
                FlatAppearance.MouseOverBackColor = Palette.Surface;
                Cursor = Cursors.Default;
                return;
            }
            Cursor = Cursors.Hand;
            if (primary)
            {
                BackColor = Palette.Accent;
                ForeColor = Palette.Bg;
                FlatAppearance.BorderColor = Palette.Accent;
                FlatAppearance.MouseOverBackColor = Palette.AccentLift;
            }
            else
            {
                BackColor = Palette.Surface;
                ForeColor = Palette.Text;
                FlatAppearance.BorderColor = Palette.Border;
                FlatAppearance.MouseOverBackColor = Palette.Border;
            }
        }
    }

    class LauncherForm : Form
    {
        // -- constants --------------------------------------------------

        const int BridgePort = 7332;
        const int ConsolePort = 3000;
        const string ConsoleUrl = "http://localhost:3000";
        const int CollapsedHeight = 392;
        const int ExpandedHeight = 660;

        static readonly string[] StepLabels = {
            "Preparing Python and Node",
            "Checking your API keys",
            "Starting the interview bridge",
            "Starting the web console",
        };

        // -- state ------------------------------------------------------

        string root;
        Process shell;
        readonly object shellLock = new object();
        volatile bool ready;
        volatile bool failed;
        volatile bool stopping;
        bool portsBusy;

        // -- widgets ----------------------------------------------------

        Panel header;
        Stepper stepper;
        FlatButton openBtn, middleBtn, stopBtn;
        TextBox log;
        Panel logWrap;
        string statusText = "Starting";
        Color statusTone = Palette.Accent;

        public LauncherForm()
        {
            Text = "Cerebrum";
            BackColor = Palette.Bg;
            ForeColor = Palette.Text;
            StartPosition = FormStartPosition.CenterScreen;
            FormBorderStyle = FormBorderStyle.FixedSingle;
            MaximizeBox = false;
            ClientSize = new Size(620, CollapsedHeight);
            try { Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath); }
            catch { }

            BuildUi();
            Shown += delegate { Begin(); };
            FormClosing += OnClosing;
        }

        // -- chrome -----------------------------------------------------

        /// Windows paints the title bar light unless a window opts in, and
        /// a dark window under a white caption bar reads as a bug. 20 is
        /// the current attribute; 19 is what it was before Windows 10 2004.
        protected override void OnHandleCreated(EventArgs e)
        {
            base.OnHandleCreated(e);
            try
            {
                int on = 1;
                if (DwmSetWindowAttribute(Handle, 20, ref on, sizeof(int)) != 0)
                    DwmSetWindowAttribute(Handle, 19, ref on, sizeof(int));
            }
            catch { }
        }

        [DllImport("dwmapi.dll", PreserveSig = true)]
        static extern int DwmSetWindowAttribute(IntPtr hwnd, int attr, ref int value, int size);

        [DllImport("uxtheme.dll", CharSet = CharSet.Unicode)]
        static extern int SetWindowTheme(IntPtr hwnd, string app, string id);

        void BuildUi()
        {
            header = new Panel();
            header.Dock = DockStyle.Top;
            header.Height = 96;
            header.BackColor = Palette.Bg;
            header.Paint += PaintHeader;

            stepper = new Stepper(StepLabels);
            stepper.Location = new Point(20, 108);
            stepper.Width = ClientSize.Width - 40;

            int by = stepper.Bottom + 14;
            openBtn = new FlatButton("Open the console", true);
            openBtn.Location = new Point(20, by);
            openBtn.Enabled = false;
            openBtn.Click += delegate { OpenConsole(); };

            middleBtn = new FlatButton("Show details", false);
            middleBtn.Location = new Point(openBtn.Right + 10, by);
            middleBtn.Click += OnMiddleClick;

            stopBtn = new FlatButton("Stop and quit", false);
            stopBtn.Location = new Point(middleBtn.Right + 10, by);
            stopBtn.Click += delegate { Close(); };

            logWrap = new Panel();
            logWrap.Location = new Point(20, by + 50);
            logWrap.Size = new Size(ClientSize.Width - 40, ExpandedHeight - by - 70);
            logWrap.BackColor = Palette.Border;   // a 1px rule, done as padding
            logWrap.Padding = new Padding(1);
            logWrap.Visible = false;

            log = new TextBox();
            log.Multiline = true;
            log.ReadOnly = true;
            log.Dock = DockStyle.Fill;
            log.ScrollBars = ScrollBars.Vertical;
            log.BorderStyle = BorderStyle.None;
            log.BackColor = Palette.Sunken;
            log.ForeColor = Palette.Muted;
            log.Font = Fonts.Mono(8.25f, FontStyle.Regular);
            log.WordWrap = false;
            log.TabStop = false;
            // A TextBox draws its scrollbar with the system theme, which is
            // light: a white bar down the side of a black pane. Explorer's
            // dark variant is the supported way to ask for the other one.
            log.HandleCreated += delegate
            {
                try { SetWindowTheme(log.Handle, "DarkMode_Explorer", null); }
                catch { }
            };
            logWrap.Controls.Add(log);

            Controls.Add(logWrap);
            Controls.Add(stopBtn);
            Controls.Add(middleBtn);
            Controls.Add(openBtn);
            Controls.Add(stepper);
            Controls.Add(header);
        }

        void PaintHeader(object sender, PaintEventArgs e)
        {
            Graphics g = e.Graphics;
            g.SmoothingMode = SmoothingMode.AntiAlias;
            g.TextRenderingHint = TextRenderingHint.ClearTypeGridFit;

            Draw.Mark(g, new Rectangle(20, 25, 40, 40));

            using (Font wordmark = Fonts.Sans(16f, FontStyle.Bold))
            using (Font sub = Fonts.Sans(8.75f, FontStyle.Regular))
            {
                TextRenderer.DrawText(g, "Cerebrum", wordmark, new Point(71, 26), Palette.Text,
                    TextFormatFlags.NoPadding);
                TextRenderer.DrawText(g, "Mock technical interviews, run locally", sub,
                    new Point(72, 51), Palette.Subtle, TextFormatFlags.NoPadding);
            }

            // Status pill, right-aligned. Colour is never the only signal -
            // it always carries the word as well.
            using (Font pill = Fonts.Sans(8.5f, FontStyle.Bold))
            {
                Size sz = TextRenderer.MeasureText(g, statusText, pill, Size.Empty,
                    TextFormatFlags.NoPadding);
                Rectangle r = new Rectangle(header.Width - 20 - sz.Width - 26, 34,
                                            sz.Width + 26, 25);
                Draw.Fill(g, r, 12, Color.FromArgb(28, statusTone));
                Draw.Outline(g, r, 12, Color.FromArgb(96, statusTone));
                TextRenderer.DrawText(g, statusText, pill, r, statusTone,
                    TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter |
                    TextFormatFlags.NoPadding);
            }

            using (Pen p = new Pen(Palette.Border))
                g.DrawLine(p, 0, header.Height - 1, header.Width, header.Height - 1);
        }

        void SetStatus(string text, Color tone)
        {
            statusText = text;
            statusTone = tone;
            header.Invalidate();
        }

        /// The middle button does one of two jobs, and says which. It is
        /// the log toggle normally, and the way out of a port clash when
        /// there is one - the only useful action in that state.
        void OnMiddleClick(object sender, EventArgs e)
        {
            if (portsBusy) { SweepAndRetry(); return; }
            bool show = !logWrap.Visible;
            logWrap.Visible = show;
            middleBtn.Text = show ? "Hide details" : "Show details";
            ClientSize = new Size(ClientSize.Width, show ? ExpandedHeight : CollapsedHeight);
        }

        void ShowLog()
        {
            if (logWrap.Visible || portsBusy) return;
            logWrap.Visible = true;
            middleBtn.Text = "Hide details";
            ClientSize = new Size(ClientSize.Width, ExpandedHeight);
        }

        // -- logging ----------------------------------------------------

        void Append(string line)
        {
            if (line == null) return;
            if (InvokeRequired) { BeginInvoke((Action<string>)Append, line); return; }
            log.AppendText(line.TrimEnd() + Environment.NewLine);
        }

        // -- lifecycle --------------------------------------------------

        void Begin()
        {
            ready = false;
            failed = false;
            portsBusy = false;
            stepper.Reset();
            openBtn.Enabled = false;
            middleBtn.Text = logWrap.Visible ? "Hide details" : "Show details";
            middleBtn.Enabled = true;
            SetStatus("Starting", Palette.Accent);

            root = ResolveRoot();
            if (root == null)
            {
                Fail("Can't find the project",
                     "This launcher has to sit inside the Cerebrum folder, or be rebuilt from it.");
                return;
            }
            Append("Cerebrum at " + root);

            // Somebody is already on these ports. A second copy would
            // half-work in a way that is miserable to diagnose, so say so
            // and offer the only two sane choices.
            if (PortOpen(BridgePort) || PortOpen(ConsolePort))
            {
                portsBusy = true;
                failed = true;
                stepper.Set(0, StepState.Blocked);
                stepper.SetDetail("Ports 7332 / 3000 are already in use.");
                SetStatus("Already up", Palette.Warn);
                Append("Something is already listening on 7332 or 3000.");
                Append("Either open the console, or clear those ports and start fresh.");
                openBtn.Enabled = true;
                middleBtn.Text = "Clear and restart";
                return;
            }

            stepper.Set(0, StepState.Active);
            stepper.SetDetail("First run builds the virtualenv and installs Node packages.");

            StartShell();
            Thread watcher = new Thread(WatchPorts);
            watcher.IsBackground = true;
            watcher.Start();
        }

        void SweepAndRetry()
        {
            middleBtn.Enabled = false;
            openBtn.Enabled = false;
            SetStatus("Clearing", Palette.Warn);
            stepper.SetDetail("Stopping whatever is holding the ports.");
            ThreadPool.QueueUserWorkItem(delegate
            {
                SweepPorts();
                BeginInvoke((Action)Begin);
            });
        }

        void StartShell()
        {
            ProcessStartInfo psi = new ProcessStartInfo();
            psi.FileName = "powershell.exe";
            // -ExecutionPolicy Bypass because the default policy on Windows
            // is Restricted, which blocks local .ps1 files outright - and a
            // launcher that fails on a stock machine is not a launcher.
            psi.Arguments = "-NoProfile -ExecutionPolicy Bypass -File \"" +
                            Path.Combine(root, "start.ps1") + "\" -NoBrowser";
            psi.WorkingDirectory = root;
            psi.UseShellExecute = false;
            psi.CreateNoWindow = true;
            psi.RedirectStandardOutput = true;
            psi.RedirectStandardError = true;
            psi.StandardOutputEncoding = Encoding.UTF8;
            psi.StandardErrorEncoding = Encoding.UTF8;

            Process p = new Process();
            p.StartInfo = psi;
            p.EnableRaisingEvents = true;
            p.OutputDataReceived += OnOutput;
            p.ErrorDataReceived += OnOutput;
            p.Exited += OnShellExited;

            try
            {
                p.Start();
            }
            catch (Exception ex)
            {
                Fail("Couldn't start PowerShell", ex.Message);
                return;
            }

            lock (shellLock) shell = p;
            p.BeginOutputReadLine();
            p.BeginErrorReadLine();
        }

        void OnOutput(object sender, DataReceivedEventArgs e)
        {
            if (e.Data == null) return;
            string line = e.Data.Trim();
            if (line.Length == 0) return;
            Append(line);
            try { BeginInvoke((Action<string>)Interpret, line); }
            catch { }   // the window can go away mid-flush on shutdown
        }

        /// Translate the script's own words into stepper positions.
        ///
        /// Progress is confirmed by the ports, not by this - a log line
        /// says a thing was attempted, a listening socket says it worked -
        /// but these lines are what fills the minutes in between.
        void Interpret(string line)
        {
            if (failed || stopping) return;

            if (line.StartsWith("No virtualenv"))
                stepper.SetDetail("Building the virtualenv - this takes a few minutes.");
            else if (line.StartsWith("Installing the console"))
                stepper.SetDetail("Installing the console's Node packages - once only.");
            else if (line.StartsWith("Checking setup"))
            {
                stepper.Set(1, StepState.Active);
                stepper.SetDetail("Every key is checked with a real call, not a format check.");
            }
            else if (line.StartsWith("Bridge"))
            {
                stepper.Set(2, StepState.Active);
                stepper.SetDetail("127.0.0.1:7332");
            }
            else if (line.StartsWith("Console"))
            {
                stepper.Set(3, StepState.Active);
                stepper.SetDetail("Compiling the console - the first build is the slow one.");
            }
            else if (line.StartsWith("Created .env"))
                Fail("Your keys are missing", "Fill in .env in the project folder, then run this again.");
            else if (line.StartsWith("Not starting"))
                Fail("The key check failed", "The details below name the key that did not answer.");
            else if (line.StartsWith("pip install failed") || line.StartsWith("Could not create"))
                Fail("Python setup failed", line);
        }

        void OnShellExited(object sender, EventArgs e)
        {
            if (stopping) return;
            try
            {
                BeginInvoke((Action)delegate
                {
                    if (stopping || failed) return;
                    Fail(ready ? "Cerebrum stopped" : "Startup failed",
                         "The start script exited. The details below say why.");
                });
            }
            catch { }
        }

        /// The honest readiness signal: a socket that accepts a connection.
        /// Whatever the log claims, this is what the browser will meet.
        void WatchPorts()
        {
            bool bridgeSeen = false;
            while (!stopping)
            {
                if (!bridgeSeen && PortOpen(BridgePort))
                {
                    bridgeSeen = true;
                    Post(delegate
                    {
                        if (failed || stopping) return;
                        stepper.Set(2, StepState.Done);
                        stepper.Set(3, StepState.Active);
                    });
                }
                if (bridgeSeen && PortOpen(ConsolePort))
                {
                    Post(MarkReady);
                    return;
                }
                Thread.Sleep(500);
            }
        }

        void Post(Action work)
        {
            try { BeginInvoke(work); }
            catch { }
        }

        void MarkReady()
        {
            if (ready || stopping || failed) return;
            ready = true;
            stepper.Set(3, StepState.Done);
            stepper.SetDetail("");
            SetStatus("Running", Palette.Ok);
            openBtn.Enabled = true;
            Append("Cerebrum is up at " + ConsoleUrl);
            OpenConsole();
        }

        void Fail(string status, string detail)
        {
            if (failed) return;
            failed = true;
            SetStatus(status, Palette.Bad);
            stepper.FailActive(detail);
            openBtn.Enabled = false;
            ShowLog();   // on a failure the log stops being detail and becomes the answer
        }

        void OpenConsole()
        {
            try { Process.Start(ConsoleUrl); }
            catch (Exception ex) { Append("Couldn't open a browser: " + ex.Message); }
        }

        // -- shutdown ---------------------------------------------------

        void OnClosing(object sender, FormClosingEventArgs e)
        {
            if (stopping) return;
            stopping = true;
            e.Cancel = true;                    // close once the tree is actually down
            SetStatus("Stopping", Palette.Warn);
            stepper.Reset();
            stepper.Set(0, StepState.Active);
            stepper.SetDetail("Putting the bridge and the console down cleanly.");
            openBtn.Enabled = false;
            stopBtn.Enabled = false;
            middleBtn.Enabled = false;

            ThreadPool.QueueUserWorkItem(delegate
            {
                StopEverything();
                Post(delegate
                {
                    FormClosing -= OnClosing;
                    Close();
                });
            });
        }

        void StopEverything()
        {
            Process p;
            lock (shellLock) p = shell;
            if (p != null)
            {
                try
                {
                    if (!p.HasExited)
                    {
                        // /T because the tree is the point: npm spawns the
                        // Next server as a child, and killing only npm
                        // leaves node holding port 3000.
                        Run("taskkill", "/T /F /PID " + p.Id);
                        p.WaitForExit(6000);
                    }
                }
                catch { }
            }
            SweepPorts();
        }

        /// Last resort. taskkill /T walks the tree it can see; anything
        /// that reparented itself is invisible to it, and the only proof
        /// the ports are free is that nothing is listening on them.
        void SweepPorts()
        {
            for (int attempt = 0; attempt < 3; attempt++)
            {
                if (!PortOpen(BridgePort) && !PortOpen(ConsolePort)) return;
                List<int> pids = ListenerPids();
                if (pids.Count == 0) return;
                foreach (int pid in pids)
                {
                    Append("Clearing leftover process " + pid);
                    Run("taskkill", "/T /F /PID " + pid);
                }
                Thread.Sleep(700);
            }
        }

        static readonly Regex NetstatLine =
            new Regex(@"TCP\s+\S+:(?:7332|3000)\s+\S+\s+LISTENING\s+(\d+)", RegexOptions.IgnoreCase);

        List<int> ListenerPids()
        {
            List<int> pids = new List<int>();
            try
            {
                ProcessStartInfo psi = new ProcessStartInfo("netstat", "-ano -p tcp");
                psi.UseShellExecute = false;
                psi.CreateNoWindow = true;
                psi.RedirectStandardOutput = true;
                using (Process p = Process.Start(psi))
                {
                    string all = p.StandardOutput.ReadToEnd();
                    p.WaitForExit(8000);
                    foreach (Match m in NetstatLine.Matches(all))
                    {
                        int pid;
                        // PID 0 and 4 are System; killing those is not an option.
                        if (int.TryParse(m.Groups[1].Value, out pid) && pid > 4 && !pids.Contains(pid))
                            pids.Add(pid);
                    }
                }
            }
            catch { }
            return pids;
        }

        static void Run(string file, string args)
        {
            try
            {
                ProcessStartInfo psi = new ProcessStartInfo(file, args);
                psi.UseShellExecute = false;
                psi.CreateNoWindow = true;
                using (Process p = Process.Start(psi)) p.WaitForExit(8000);
            }
            catch { }
        }

        // -- helpers ----------------------------------------------------

        static bool PortOpen(int port)
        {
            try
            {
                using (TcpClient c = new TcpClient())
                {
                    IAsyncResult r = c.BeginConnect("127.0.0.1", port, null, null);
                    if (!r.AsyncWaitHandle.WaitOne(300)) return false;
                    c.EndConnect(r);
                    return true;
                }
            }
            catch { return false; }
        }

        /// Walk up from the binary looking for the project, then fall back
        /// to where it was built. The walk is what matters when the repo
        /// has been moved or cloned somewhere else; the baked path is what
        /// lets a copy of the .exe sitting on the desktop still work.
        static string ResolveRoot()
        {
            string dir = Path.GetDirectoryName(Application.ExecutablePath);
            for (int i = 0; i < 6 && !string.IsNullOrEmpty(dir); i++)
            {
                if (IsRoot(dir)) return dir;
                DirectoryInfo up = Directory.GetParent(dir);
                dir = up == null ? null : up.FullName;
            }
            if (IsRoot(BuildInfo.RepoRoot)) return BuildInfo.RepoRoot;
            return null;
        }

        static bool IsRoot(string dir)
        {
            return !string.IsNullOrEmpty(dir)
                && File.Exists(Path.Combine(dir, "start.ps1"))
                && Directory.Exists(Path.Combine(dir, "backend"));
        }

        [STAThread]
        static void Main()
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new LauncherForm());
        }
    }
}
