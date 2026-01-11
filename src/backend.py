import subprocess
import os
import time

class CryptomatorBackend:
    _instances = {} # Map vault_path -> (Popen process, mount_path)

    @classmethod
    def unlock(cls, vault_path, password, mount_point=None):
        if vault_path in cls._instances:
              # Already unlocked?
              return True, cls._instances[vault_path][1]

        # Ensure mount point exists ON THE HOST (not in sandbox)
        if not mount_point:
            # Use ~/mnt/cryptomator/ directory
            home_dir = os.path.expanduser('~')
            mount_base = os.path.join(home_dir, "mnt", "cryptomator")
            vault_name = os.path.basename(vault_path)
            mount_point = os.path.join(mount_base, vault_name)
        
        # Create mount point directory on the host using flatpak-spawn
        try:
            subprocess.run(['flatpak-spawn', '--host', 'mkdir', '-p', mount_point], check=True)
            print(f"DEBUG: Created mount point on host: {mount_point}", flush=True)
        except Exception as e:
            print(f"DEBUG: Failed to create mount point on host: {e}", flush=True)
            # Try to create in sandbox as fallback
            try:
                os.makedirs(mount_point, exist_ok=True)
            except Exception as e2:
                print(f"ERROR: Cannot create mount point: {e2}", flush=True)
                return False, None

        # Use FUSE mounter with flatpak-spawn to run fusermount on host
        cmd = [
            'cryptomator-cli',
            'unlock',
            '--password:stdin',
            '--mounter=org.cryptomator.frontend.fuse.mount.LinuxFuseMountProvider',
            f'--mountPoint={mount_point}',
            vault_path
        ]
        
        try:
            # Start process
            print(f"DEBUG: Running command: {' '.join(cmd)}", flush=True)
            print(f"DEBUG: Mount point: {mount_point}", flush=True)
            
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Send password
            print(f"DEBUG: Unlocking {vault_path} with password len={len(password)}", flush=True)
            
            # Use communicate() which is safer than manual stdin/stdout handling
            try:
                stdout, stderr = proc.communicate(input=password + "\n", timeout=5)
                # Process exited within timeout
                print(f"DEBUG: Process exited with code {proc.returncode}", flush=True)
                print(f"DEBUG: STDOUT: {stdout}", flush=True)
                print(f"DEBUG: STDERR: {stderr}", flush=True)
                if proc.returncode != 0:
                    print(f"Unlock failed with exit code {proc.returncode}", flush=True)
                    return False, None
                else:
                    print(f"DEBUG: Process exited successfully but quickly - might have daemonized", flush=True)
                    return False, None
            except subprocess.TimeoutExpired:
                # Process is still running after timeout -> Success (FUSE mount is active)
                print(f"DEBUG: Process still running after timeout - mount successful!", flush=True)
                print(f"DEBUG: Vault mounted at: {mount_point}", flush=True)
                
                cls._instances[vault_path] = (proc, mount_point)
                return True, mount_point
                
        except Exception as e:
            print(f"Error unlocking: {e}", flush=True)
            import traceback
            traceback.print_exc()
            return False, None
            
        return False, None

    @classmethod
    def is_mounted(cls, vault_path, mount_point):
        """Check if a vault is currently mounted at the given mount point"""
        if not mount_point or not os.path.exists(mount_point):
            return False
        
        # Check if the mount point is a FUSE mount using /proc/mounts
        try:
            with open('/proc/mounts', 'r') as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2:
                        mounted_path = parts[1]
                        if mounted_path == mount_point:
                            return True
        except Exception as e:
            print(f"DEBUG: Error checking if mounted: {e}", flush=True)
        
        return False
    
    @classmethod
    def lock(cls, vault_path):
        if vault_path in cls._instances:
            proc, mount_path = cls._instances[vault_path]
            # Terminate process to unmount
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            
            del cls._instances[vault_path]
            
            # Clean up mount point directory
            try:
                vault_name = os.path.basename(mount_path)
                home_dir = os.path.expanduser('~')
                cryptomator_base = os.path.join(home_dir, "mnt", "cryptomator")
                mnt_base = os.path.join(home_dir, "mnt")
                
                # Remove the vault-specific directory
                subprocess.run(['flatpak-spawn', '--host', 'rmdir', mount_path], check=False)
                
                # Check if cryptomator directory is empty and remove it
                try:
                    result = subprocess.run(['flatpak-spawn', '--host', 'ls', '-A', cryptomator_base], 
                                          capture_output=True, text=True)
                    if not result.stdout.strip():
                        subprocess.run(['flatpak-spawn', '--host', 'rmdir', cryptomator_base], check=False)
                        
                        # Check if mnt directory is empty and remove it
                        result = subprocess.run(['flatpak-spawn', '--host', 'ls', '-A', mnt_base], 
                                              capture_output=True, text=True)
                        if not result.stdout.strip():
                            subprocess.run(['flatpak-spawn', '--host', 'rmdir', mnt_base], check=False)
                except Exception:
                    pass
            except Exception as e:
                print(f"DEBUG: Failed to clean up mount point: {e}", flush=True)
            
            return True
        return False
    
    @classmethod
    def create_vault(cls, vault_path, password):
        """
        Create a new Cryptomator vault at the specified path.
        Note: This requires the cryptomator-cli or official app to properly initialize.
        For now, we'll direct users to create vaults with the official application.
        
        Returns: (success: bool, error_message: str)
        """
        # Since cryptomator-cli doesn't support vault creation and properly
        # creating the masterkey requires the Cryptomator crypto library,
        # we recommend using the official Cryptomator application
        return False, "Vault creation is not yet supported. Please use the official Cryptomator application to create new vaults, then add them here."
