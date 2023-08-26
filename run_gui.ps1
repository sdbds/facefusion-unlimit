$execution_provider="cuda"
$execution_thread_count=128
$execution_queue_count=8
$temp_frame_quality=100
$output_video_quality=100
$ui_layouts=""
$max_memory=""

Set-Location $PSScriptRoot
.\venv\Scripts\activate

$Env:HF_HOME = "./huggingface"
$ext_args = [System.Collections.ArrayList]::new()

if ($ui_layouts) {
  [void]$ext_args.Add("--ui-layouts=$ui_layouts")
}

if ($max_memory) {
  [void]$ext_args.Add("--max-memory=$max_memory")
}

python.exe run.py `
--frame-processor face_swapper face_enhancer `
--keep-fps `
--keep-temp `
--execution-provider=$execution_provider `
--execution-queue-count=$execution_queue_count `
--execution-thread-count=$execution_thread_count `
--temp-frame-quality=$temp_frame_quality `
--output-video-quality=$output_video_quality $ext_args
