// Small Windows entry point for the existing Python notebook launcher.
using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Windows.Forms;

internal static class NotebookLauncher
{
    private static string Quote(string value)
    {
        var result = new StringBuilder("\"");
        int slashes = 0;
        foreach (char character in value)
        {
            if (character == '\\') { slashes++; continue; }
            if (character == '"')
                result.Append('\\', slashes * 2 + 1).Append('"');
            else
                result.Append('\\', slashes).Append(character);
            slashes = 0;
        }
        return result.Append('\\', slashes * 2).Append('"').ToString();
    }

    [STAThread]
    private static int Main(string[] args)
    {
        bool check = Array.IndexOf(args, "--check") >= 0;
        string logPath = null;
        try
        {
            string root = AppDomain.CurrentDomain.BaseDirectory;
            if (!File.Exists(Path.Combine(root, "notebook_launcher.py")))
                root = __CHECKOUT_ROOT__;
            string script = Path.Combine(root, "notebook_launcher.py");
            if (!File.Exists(script))
                throw new FileNotFoundException("The notebook tools folder has moved. Rebuild this launcher.", script);

            string python = Environment.GetEnvironmentVariable("JOURNAL_TOOLS_PYTHON");
            if (String.IsNullOrWhiteSpace(python))
            {
                python = Path.Combine(root, ".venv", "Scripts", "pythonw.exe");
                if (!File.Exists(python)) python = __PYTHON_EXECUTABLE__;
            }
            if (!File.Exists(python))
                throw new FileNotFoundException("Python was not found. Rebuild the app with the project's Python environment.", python);

            string logDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                                         "Journal Analysis Tools", "Logs");
            Directory.CreateDirectory(logDir);
            logPath = Path.Combine(logDir, "launcher.log");
            var arguments = new StringBuilder(Quote(script));
            foreach (string argument in args) arguments.Append(' ').Append(Quote(argument));
            var start = new ProcessStartInfo(python, arguments.ToString());
            start.WorkingDirectory = root;
            start.UseShellExecute = false;
            start.CreateNoWindow = true;
            start.RedirectStandardOutput = true;
            start.RedirectStandardError = true;
            start.StandardOutputEncoding = Encoding.UTF8;
            start.StandardErrorEncoding = Encoding.UTF8;
            start.EnvironmentVariables["PYTHONUTF8"] = "1";
            using (var writer = new StreamWriter(new FileStream(logPath, FileMode.Append,
                                                               FileAccess.Write, FileShare.ReadWrite), Encoding.UTF8))
            using (TextWriter log = TextWriter.Synchronized(writer))
            using (var process = new Process())
            {
                writer.AutoFlush = true;
                process.StartInfo = start;
                process.OutputDataReceived += (sender, output) => { if (output.Data != null) log.WriteLine(output.Data); };
                process.ErrorDataReceived += (sender, output) => { if (output.Data != null) log.WriteLine(output.Data); };
                process.Start();
                process.BeginOutputReadLine();
                process.BeginErrorReadLine();
                process.WaitForExit();
                if (process.ExitCode != 0 && !check)
                    MessageBox.Show("The launcher could not start. See:\n" + logPath +
                                    "\n\nInstall requirements.txt in the project's Python environment.",
                                    "Journal Notebook Launcher", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return process.ExitCode;
            }
        }
        catch (Exception error)
        {
            if (logPath != null)
            {
                try { File.AppendAllText(logPath, error + Environment.NewLine); }
                catch (IOException) { }
                catch (UnauthorizedAccessException) { }
            }
            if (!check)
                MessageBox.Show(error.Message, "Journal Notebook Launcher", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }
}
