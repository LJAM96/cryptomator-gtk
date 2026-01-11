import subprocess
import os
import signal

class CryptomatorBackend:
    _instances = {} # Map vault_path -> Popen process

    @classmethod
    def unlock(cls, vault_path, password, mount_point):
        if vault_path in cls._instances:
             # Already unlocked?
             return True

        # Ensure mount point exists
        os.makedirs(mount_point, exist_ok=True)

        # WebDAV mounter doesn't support --mountPoint, it auto-mounts via GIO
        cmd = [
            'cryptomator-cli',
            'unlock',
            '--password:stdin',
            '--mounter=org.cryptomator.frontend.webdav.mount.LinuxGioMounter',
            vault_path
        ]
        
        try:
            # Start process
            print(f"DEBUG: Running command: {' '.join(cmd)}", flush=True)
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Send password
            try:
                print(f"DEBUG: Unlocking {vault_path} with password len={len(password)} at {mount_point}", flush=True)
                
                proc.stdin.write(password + "\n")
                proc.stdin.flush()
                proc.stdin.close() # Explicitly close stdin to signal EOF
                
                # Wait briefly to catch immediate errors (e.g. wrong password)
                # If command finishes within 2 seconds, it probably failed 
                # (or maybe it daemonizes? CLI usually blocks)
                proc.wait(timeout=2)
                
                # If we get here, process exited
                stdout = proc.stdout.read()
                stderr = proc.stderr.read()
                print(f"DEBUG: Process exited with code {proc.returncode}", flush=True)
                print(f"DEBUG: STDOUT: {stdout}", flush=True)
                print(f"DEBUG: STDERR: {stderr}", flush=True)
                if proc.returncode != 0:
                    print(f"Unlock failed: {stderr}", flush=True)
                    return False
                else:
                    # Successfully exited - maybe it daemonized?
                    print(f"DEBUG: Process exited successfully but immediately", flush=True)
                    return False
            except subprocess.TimeoutExpired:
                # Process is still running -> Success (Mount holds foreground)
                print(f"DEBUG: Process still running after 2s, assuming success", flush=True)
                cls._instances[vault_path] = proc
                return True
                
        except Exception as e:
            print(f"Error unlocking: {e}", flush=True)
            import traceback
            traceback.print_exc()
            return False
            
        return False

    @classmethod
    def lock(cls, vault_path):
        if vault_path in cls._instances:
            proc = cls._instances[vault_path]
            # Terminate process to unmount
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            
            del cls._instances[vault_path]
            return True
        return False

